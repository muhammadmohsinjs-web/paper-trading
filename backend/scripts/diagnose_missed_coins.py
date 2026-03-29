"""Trace missed coins through the scanner and strategy pipeline."""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.engine.composite_scorer import CompositeScoreResult, compute_composite_score
from app.engine.tradability import (
    TradabilityResult,
    build_tradability_metrics,
    evaluate_movement_quality,
    evaluate_symbol_tradability,
    is_stablecoin_symbol,
)
from app.market.binance_rest import fetch_candles
from app.market.data_store import Candle, DataStore
from app.market.indicators import compute_indicators
from app.regime.classifier import RegimeClassifier
from app.regime.types import DetailedRegime, RegimeResult
from app.scanner.families import (
    FAMILY_ALLOWED_REGIMES,
    SETUP_TO_FAMILY,
    validate_setup_family,
)
from app.scanner.universe_selector import UniverseSelector
from app.strategies.bollinger_bounce import BollingerBounceStrategy
from app.strategies.hybrid_composite import HybridCompositeStrategy
from app.strategies.macd_momentum import MACDMomentumStrategy
from app.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from app.strategies.sma_crossover import SMACrossoverStrategy

TARGETS = [
    {"symbol": "NOMUSDT", "move_pct": 52.78, "price": 0.00275},
    {"symbol": "STOUSDT", "move_pct": 29.60, "price": 0.1445},
    {"symbol": "ONTUSDT", "move_pct": 21.41, "price": 0.06068},
]

INDICATOR_CONFIG = {
    "sma_short": 10,
    "sma_long": 50,
    "rsi_period": 14,
    "volume_ma_period": 20,
}

SETTINGS = get_settings()
SEP = "=" * 70


@dataclass(frozen=True)
class RankedCandidate:
    symbol: str
    activity_score: float
    volume_surge: float
    volatility_quality: float
    trend_clarity: float
    liquidity_depth: float
    relative_strength: float
    volume_24h_usdt: float
    tradability: TradabilityResult


@dataclass(frozen=True)
class UniverseReference:
    candidate_symbols: set[str]
    ranked_candidates: list[RankedCandidate]
    selected_symbols: set[str]
    cutoff_score: float | None
    candidate_count: int

    @property
    def ranked_count(self) -> int:
        return len(self.ranked_candidates)

    def rank_for(self, symbol: str) -> int | None:
        for idx, candidate in enumerate(self.ranked_candidates, start=1):
            if candidate.symbol == symbol:
                return idx
        return None

    def score_for(self, symbol: str) -> RankedCandidate | None:
        for candidate in self.ranked_candidates:
            if candidate.symbol == symbol:
                return candidate
        return None


def tag(passed: bool) -> str:
    return "\033[92m[PASS]\033[0m" if passed else "\033[91m[FAIL]\033[0m"


def warn(text: str) -> str:
    return f"\033[93m[WARN]\033[0m {text}"


def fmt_optional(value: float | None, digits: int = 4, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}{suffix}"


def reset_runtime_state() -> None:
    DataStore.reset()
    UniverseSelector.reset()


async def fetch_ticker_24h(symbol: str) -> dict[str, Any] | None:
    url = f"{SETTINGS.binance_rest_url}/api/v3/ticker/24hr"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params={"symbol": symbol})
        if response.status_code == 400:
            return None
        response.raise_for_status()
        return response.json()


async def fetch_exchange_info(symbol: str) -> dict[str, Any] | None:
    url = f"{SETTINGS.binance_rest_url}/api/v3/exchangeInfo"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params={"symbol": symbol})
        if response.status_code == 400:
            return None
        response.raise_for_status()
        payload = response.json()
        symbols = payload.get("symbols", [])
        return symbols[0] if symbols else None


def split_candles(candles: list[Candle]) -> tuple[list[float], list[float], list[float], list[float]]:
    closes = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    volumes = [candle.volume for candle in candles]
    return closes, highs, lows, volumes


def compute_activity_components(
    symbol: str,
    volume_24h: float,
    price: float,
    store: DataStore,
) -> dict[str, float]:
    volume_surge = UniverseSelector._score_volume_surge(symbol, volume_24h, store)
    volatility_quality = UniverseSelector._score_volatility_quality(symbol, price, store)
    trend_clarity = UniverseSelector._score_trend_clarity(symbol, store)
    liquidity_depth = UniverseSelector._score_liquidity_depth(volume_24h)
    relative_strength = UniverseSelector._score_relative_strength(symbol)
    composite = (
        volume_surge * SETTINGS.universe_volume_surge_weight
        + volatility_quality * SETTINGS.universe_volatility_quality_weight
        + trend_clarity * SETTINGS.universe_trend_clarity_weight
        + liquidity_depth * SETTINGS.universe_liquidity_depth_weight
        + relative_strength * SETTINGS.universe_relative_strength_weight
    )
    return {
        "volume_surge": volume_surge,
        "volatility_quality": volatility_quality,
        "trend_clarity": trend_clarity,
        "liquidity_depth": liquidity_depth,
        "relative_strength": relative_strength,
        "composite": composite,
    }


async def build_universe_reference() -> UniverseReference:
    selector = UniverseSelector.get_instance()
    await selector.get_active_universe(force_refresh=True)

    tickers = await UniverseSelector._fetch_all_tickers()
    ticker_map = {ticker["symbol"]: ticker for ticker in tickers}
    store = DataStore.get_instance()

    ranked_candidates: list[RankedCandidate] = []
    candidate_symbols = {candidate.symbol for candidate in selector._candidate_pool}

    for candidate in selector._candidate_pool:
        ticker = ticker_map.get(candidate.symbol)
        if ticker is None:
            continue

        candles = store.get_candles(candidate.symbol, "1h", 200)
        if len(candles) < 50:
            try:
                candles = await fetch_candles(symbol=candidate.symbol, interval="1h", limit=200)
            except Exception:
                continue
            store.set_candles(candidate.symbol, "1h", candles)
        if len(candles) < 50:
            continue

        closes, highs, lows, volumes = split_candles(candles)
        volume_24h = float(ticker.get("quoteVolume", 0.0))
        price = float(ticker.get("lastPrice", 0.0))
        tradability = evaluate_symbol_tradability(
            symbol=candidate.symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            volume_24h_usdt=volume_24h,
        )
        if not tradability.passed:
            continue

        components = compute_activity_components(candidate.symbol, volume_24h, price, store)
        ranked_candidates.append(
            RankedCandidate(
                symbol=candidate.symbol,
                activity_score=round(components["composite"], 4),
                volume_surge=round(components["volume_surge"], 4),
                volatility_quality=round(components["volatility_quality"], 4),
                trend_clarity=round(components["trend_clarity"], 4),
                liquidity_depth=round(components["liquidity_depth"], 4),
                relative_strength=round(components["relative_strength"], 4),
                volume_24h_usdt=volume_24h,
                tradability=tradability,
            )
        )

    ranked_candidates.sort(key=lambda candidate: candidate.activity_score, reverse=True)
    selected = ranked_candidates[: SETTINGS.dynamic_universe_size]
    cutoff_score = selected[-1].activity_score if selected else None
    selected_symbols = {candidate.symbol for candidate in selected}
    return UniverseReference(
        candidate_symbols=candidate_symbols,
        ranked_candidates=ranked_candidates,
        selected_symbols=selected_symbols,
        cutoff_score=cutoff_score,
        candidate_count=len(candidate_symbols),
    )


async def check_hard_filters(symbol: str, universe_reference: UniverseReference | None) -> tuple[bool, dict[str, Any]]:
    ticker = await fetch_ticker_24h(symbol)
    info = await fetch_exchange_info(symbol)
    if ticker is None or info is None:
        print(f"  Symbol {symbol} not found on Binance {tag(False)}")
        return False, {}

    price = float(ticker.get("lastPrice", 0.0))
    volume_24h = float(ticker.get("quoteVolume", 0.0))
    price_change_pct = float(ticker.get("priceChangePercent", 0.0))
    status = info.get("status", "UNKNOWN")
    quote_asset = info.get("quoteAsset", "")
    spot_allowed = bool(info.get("isSpotTradingAllowed", False))
    onboard_date = info.get("onboardDate")
    age_days = 999.0 if not onboard_date else (time.time() * 1000 - onboard_date) / (86_400 * 1000)
    stable_ok = not is_stablecoin_symbol(symbol)

    price_ok = price >= SETTINGS.universe_min_price
    volume_ok = volume_24h >= SETTINGS.universe_min_24h_volume_usdt
    age_ok = age_days >= SETTINGS.universe_min_listing_age_days
    status_ok = status == "TRADING" and quote_asset == "USDT" and spot_allowed

    print(f"  Price:            ${price:.8f} >= ${SETTINGS.universe_min_price:.5f} {tag(price_ok)}")
    print(f"  24h Volume:       ${volume_24h:,.0f} >= ${SETTINGS.universe_min_24h_volume_usdt:,.0f} {tag(volume_ok)}")
    print(f"  Listing Age:      {age_days:.1f}d >= {SETTINGS.universe_min_listing_age_days}d {tag(age_ok)}")
    print(f"  Market Status:    {status} / {quote_asset} / spot={spot_allowed} {tag(status_ok)}")
    print(f"  Stablecoin Check: {symbol.replace('USDT', '')} {tag(stable_ok)}")
    print(f"  24h Change:       {price_change_pct:+.2f}%")

    if universe_reference is not None:
        in_candidate_pool = symbol in universe_reference.candidate_symbols
        print(f"  Candidate Pool:   {'present' if in_candidate_pool else 'absent'} {tag(in_candidate_pool)}")

    passed = price_ok and volume_ok and age_ok and status_ok and stable_ok
    print(f"  >>> Stage 1 overall: {tag(passed)}")
    return passed, {
        "price": price,
        "volume_24h": volume_24h,
        "price_change_pct": price_change_pct,
        "age_days": age_days,
    }


def check_activity_ranking(
    symbol: str,
    volume_24h: float,
    price: float,
    store: DataStore,
    universe_reference: UniverseReference | None,
) -> dict[str, float]:
    components = compute_activity_components(symbol, volume_24h, price, store)
    print(f"  Volume Surge:       {components['volume_surge']:.4f} (weight {SETTINGS.universe_volume_surge_weight:.0%})")
    print(f"  Volatility Quality: {components['volatility_quality']:.4f} (weight {SETTINGS.universe_volatility_quality_weight:.0%})")
    print(f"  Trend Clarity:      {components['trend_clarity']:.4f} (weight {SETTINGS.universe_trend_clarity_weight:.0%})")
    print(f"  Liquidity Depth:    {components['liquidity_depth']:.4f} (weight {SETTINGS.universe_liquidity_depth_weight:.0%})")
    print(f"  Relative Strength:  {components['relative_strength']:.4f} (weight {SETTINGS.universe_relative_strength_weight:.0%})")
    print(f"  Composite Score:    {components['composite']:.4f}")

    if universe_reference is None:
        likely_in = components["composite"] >= 0.25
        print(f"  Top-{SETTINGS.dynamic_universe_size} Cut: fallback threshold 0.2500 {tag(likely_in)}")
        return components

    cutoff = universe_reference.cutoff_score
    rank = universe_reference.rank_for(symbol)
    selected = symbol in universe_reference.selected_symbols
    print(f"  Ranked Symbols:     {universe_reference.ranked_count}")
    if cutoff is not None:
        print(f"  Actual Cutoff:      {cutoff:.4f}")
    if rank is not None:
        print(f"  Actual Rank:        {rank}/{universe_reference.ranked_count}")
    else:
        print("  Actual Rank:        not ranked")
    if cutoff is not None:
        print(f"  Top-{SETTINGS.dynamic_universe_size} Inclusion: {tag(selected)}")
    if rank is None:
        print(f"  {warn('Symbol was not in the ranked tradable set, so ranking could not rescue it')}")
    elif not selected and cutoff is not None:
        print(f"  Needed >= {cutoff:.4f}, got {components['composite']:.4f}")
    return components


def check_tradability(
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    volume_24h: float,
) -> TradabilityResult:
    result = evaluate_symbol_tradability(
        symbol=symbol,
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        volume_24h_usdt=volume_24h,
    )
    metrics = result.metrics

    print(
        f"  ATR% (14):          {metrics.atr_pct_14:.4f}% >= {SETTINGS.trade_quality_min_atr_pct:.2f}% "
        f"{tag(metrics.atr_pct_14 >= SETTINGS.trade_quality_min_atr_pct)}"
    )
    print(
        f"  Range% (20):        {metrics.range_pct_20:.4f}% >= {SETTINGS.trade_quality_min_range_pct_20:.2f}% "
        f"{tag(metrics.range_pct_20 >= SETTINGS.trade_quality_min_range_pct_20)}"
    )
    print(
        f"  Range% (24h):       {metrics.range_pct_24h:.4f}% >= {SETTINGS.trade_quality_min_range_pct_24h:.2f}% "
        f"{tag(metrics.range_pct_24h >= SETTINGS.trade_quality_min_range_pct_24h)}"
    )
    print(
        f"  Abs Change% (24h):  {metrics.abs_change_pct_24h:.4f}% >= {SETTINGS.trade_quality_min_abs_change_pct_24h:.2f}% "
        f"{tag(metrics.abs_change_pct_24h >= SETTINGS.trade_quality_min_abs_change_pct_24h)}"
    )
    print(
        f"  Close Std% (24h):   {metrics.close_std_pct_24h:.4f}% >= {SETTINGS.trade_quality_min_close_std_pct_24h:.2f}% "
        f"{tag(metrics.close_std_pct_24h >= SETTINGS.trade_quality_min_close_std_pct_24h)}"
    )
    print(
        f"  Market Quality:     {metrics.market_quality_score:.4f} >= {SETTINGS.trade_quality_min_market_quality_score:.2f} "
        f"{tag(metrics.market_quality_score >= SETTINGS.trade_quality_min_market_quality_score)}"
    )
    print(f"  Volume Ratio:       {metrics.volume_ratio:.4f}")
    print(f"  Reward/Cost Ratio:  {metrics.reward_to_cost_ratio:.4f}")
    print(f"  Near-Peg Score:     {metrics.near_peg_score:.4f}")
    print(f"  Directional Move:   {metrics.directional_displacement_pct_10:.4f}%")
    print(f"  EMA Spread:         {metrics.ema_spread_pct:.4f}%")
    print(f"  BB Width:           {metrics.bb_width_pct:.4f}%")
    print(f"  Reason Codes:       {', '.join(result.reason_codes) if result.reason_codes else 'none'}")
    print(f"  >>> Stage 3 overall: {tag(result.passed)}")
    if not result.passed:
        print(f"      {result.reason_text}")
    return result


def print_indicators(indicators: dict[str, Any]) -> None:
    rsi_values = indicators.get("rsi", [])
    macd_line, signal_line, histogram = indicators.get("macd", ([], [], []))
    sma_short = indicators.get("sma_short", [])
    sma_long = indicators.get("sma_long", [])
    bb_upper, bb_middle, bb_lower = indicators.get("bollinger_bands", ([], [], []))
    adx_values = indicators.get("adx", [])
    volume_ratio = indicators.get("volume_ratio", [])

    print(f"  RSI(14):        {fmt_optional(rsi_values[-1] if rsi_values else None, 2)}")
    if macd_line and signal_line and histogram:
        print(
            "  MACD:           "
            f"line={macd_line[-1]:.6f} signal={signal_line[-1]:.6f} hist={histogram[-1]:.6f}"
        )
    else:
        print("  MACD:           N/A")
    print(f"  SMA(10):        {fmt_optional(sma_short[-1] if sma_short else None, 6)}")
    print(f"  SMA(50):        {fmt_optional(sma_long[-1] if sma_long else None, 6)}")
    if bb_upper and bb_middle and bb_lower:
        print(f"  BB Upper:       {bb_upper[-1]:.6f}")
        print(f"  BB Middle:      {bb_middle[-1]:.6f}")
        print(f"  BB Lower:       {bb_lower[-1]:.6f}")
    else:
        print("  Bollinger:      N/A")
    print(f"  ADX(14):        {fmt_optional(adx_values[-1] if adx_values else None, 2)}")
    print(f"  Volume Ratio:   {fmt_optional(volume_ratio[-1] if volume_ratio else None, 4)}")


def check_regime(indicators: dict[str, Any]) -> RegimeResult:
    result = RegimeClassifier().classify_full(indicators)
    print(f"  Coarse Regime:    {result.regime.value}")
    print(f"  Detailed Regime:  {result.detailed_regime.value if result.detailed_regime else 'N/A'}")
    print(f"  Direction:        {result.direction or 'N/A'}")
    print(f"  Confidence:       {result.confidence:.4f}")
    print(f"  Exhaustion:       {result.exhaustion_score:.4f}")
    print(f"  Volatility Z:     {result.volatility_z_score:.4f}")
    print(f"  Reasoning:        {result.reasoning}")
    print("  Allowed Families:")
    for family, allowed_regimes in FAMILY_ALLOWED_REGIMES.items():
        allowed = result.detailed_regime in allowed_regimes if result.detailed_regime else True
        print(f"    {family.value:24s} {tag(allowed)}")
    return result


def describe_sma_no_signal(indicators: dict[str, Any]) -> str:
    sma_short = indicators.get("sma_short", [])
    sma_long = indicators.get("sma_long", [])
    if len(sma_short) < 2 or len(sma_long) < 2:
        return "not enough SMA history"
    prev_gap = sma_short[-2] - sma_long[-2]
    curr_gap = sma_short[-1] - sma_long[-1]
    if prev_gap <= 0 < curr_gap:
        volume_ratio = indicators.get("volume_ratio", [])
        latest_volume_ratio = volume_ratio[-1] if volume_ratio else None
        if latest_volume_ratio is not None and latest_volume_ratio < 0.8:
            return f"bullish cross rejected by low volume ratio ({latest_volume_ratio:.4f})"
    return f"no fresh bullish crossover (gap {curr_gap:.6f})"


def describe_rsi_no_signal(indicators: dict[str, Any]) -> str:
    rsi_values = indicators.get("rsi", [])
    if len(rsi_values) < 2:
        return "not enough RSI history"
    current_rsi = rsi_values[-1]
    divergence = indicators.get("rsi_divergence")
    has_bullish_divergence = (
        divergence is not None
        and getattr(divergence, "detected", False)
        and getattr(divergence, "divergence_type", "") == "bullish"
    )
    if 25 <= current_rsi < 35 and not has_bullish_divergence:
        return f"RSI={current_rsi:.1f} is weakly oversold without bullish divergence"
    if current_rsi >= 35:
        return f"RSI={current_rsi:.1f} is not oversold"
    return f"RSI={current_rsi:.1f} did not meet deep-oversold or divergence trigger"


def describe_macd_no_signal(indicators: dict[str, Any]) -> str:
    macd_line, signal_line, histogram = indicators.get("macd", ([], [], []))
    if len(macd_line) < 2 or len(signal_line) < 2 or len(histogram) < 2:
        return "not enough MACD history"
    if macd_line[-1] > signal_line[-1]:
        return "MACD is already above signal but no fresh bullish cross on this bar"
    return "MACD is below signal line"


def describe_bollinger_no_signal(indicators: dict[str, Any]) -> str:
    upper, middle, lower = indicators.get("bollinger_bands", ([], [], []))
    latest_close = indicators.get("latest_close")
    if not upper or not middle or not lower or latest_close is None:
        return "not enough Bollinger data"
    band_width = upper[-1] - lower[-1]
    if band_width <= 0:
        return "invalid band width"
    proximity = (latest_close - lower[-1]) / band_width
    return f"price is {proximity:.1%} above the lower band"


def describe_hybrid_no_signal(composite_result: CompositeScoreResult) -> str:
    if composite_result.signal != "HOLD":
        return "signal available"
    if composite_result.reject_reason_codes:
        return ", ".join(composite_result.reject_reason_codes)
    return f"direction={composite_result.direction} confidence={composite_result.confidence:.4f}"


def print_strategy_result(name: str, signal: Any, no_signal_reason: str) -> None:
    if signal is None:
        print(f"  {name:22s} [NO SIGNAL] {no_signal_reason}")
        return
    action = signal.action.value if hasattr(signal.action, "value") else str(signal.action)
    print(f"  {name:22s} [{action}] {signal.reason}")


def check_strategies(
    indicators: dict[str, Any],
    composite_result: CompositeScoreResult,
) -> None:
    available_usdt = Decimal("1000")
    print_strategy_result(
        "SMA Crossover",
        SMACrossoverStrategy().decide(indicators, has_position=False, available_usdt=available_usdt),
        describe_sma_no_signal(indicators),
    )
    print_strategy_result(
        "RSI Mean Reversion",
        RSIMeanReversionStrategy().decide(indicators, has_position=False, available_usdt=available_usdt),
        describe_rsi_no_signal(indicators),
    )
    print_strategy_result(
        "MACD Momentum",
        MACDMomentumStrategy().decide(indicators, has_position=False, available_usdt=available_usdt),
        describe_macd_no_signal(indicators),
    )
    print_strategy_result(
        "Bollinger Bounce",
        BollingerBounceStrategy().decide(indicators, has_position=False, available_usdt=available_usdt),
        describe_bollinger_no_signal(indicators),
    )
    print_strategy_result(
        "Hybrid Composite",
        HybridCompositeStrategy().decide(indicators, has_position=False, available_usdt=available_usdt),
        describe_hybrid_no_signal(composite_result),
    )


def check_composite(
    indicators: dict[str, Any],
    regime_result: RegimeResult,
    tradability_result: TradabilityResult,
) -> CompositeScoreResult:
    movement_quality = evaluate_movement_quality(direction="BUY", metrics=tradability_result.metrics)
    composite_result = compute_composite_score(
        indicators,
        regime=regime_result.regime.value,
        market_quality_score=tradability_result.metrics.market_quality_score,
        movement_quality_score=movement_quality.score,
    )
    print(f"  Direction:         {composite_result.direction}")
    print(f"  Signal:            {composite_result.signal}")
    print(f"  Composite Score:   {composite_result.composite_score:.4f}")
    print(f"  Directional Score: {composite_result.directional_score:.4f}")
    print(f"  Confidence:        {composite_result.confidence:.4f}")
    print(f"  Edge Strength:     {composite_result.edge_strength:.4f}")
    print(f"  Market Quality:    {composite_result.market_quality:.4f}")
    print(f"  Regime Alignment:  {composite_result.regime_alignment:.4f}")
    print(f"  Signal Agreement:  {composite_result.signal_agreement:.4f}")
    print(f"  Dampening:         {composite_result.dampening_multiplier:.4f}")
    print(f"  Edge Floor:        {tag(composite_result.edge_floor_passed)}")
    print(f"  Quality Floor:     {tag(composite_result.quality_floor_passed)}")
    print("  Votes:")
    for key, vote in composite_result.votes.items():
        print(f"    {key:12s} vote={vote:+.4f} weight={composite_result.weights.get(key, 0.0):.4f}")
    print(
        "  Reject Reasons:    "
        f"{', '.join(composite_result.reject_reason_codes) if composite_result.reject_reason_codes else 'none'}"
    )
    print(
        f"  Movement Quality:  {movement_quality.score:.4f} "
        f"{tag(movement_quality.passed)}"
    )
    if not movement_quality.passed:
        print(f"    Primary block: {movement_quality.reason_text}")
    return composite_result


def detect_setups(indicators: dict[str, Any]) -> list[tuple[str, str]]:
    detected: list[tuple[str, str]] = []
    rsi_values = indicators.get("rsi", [])
    macd_line, signal_line, histogram = indicators.get("macd", ([], [], []))
    sma_short = indicators.get("sma_short", [])
    sma_long = indicators.get("sma_long", [])
    volume_ratio = indicators.get("volume_ratio", [])
    adx_values = indicators.get("adx", [])
    ema_12 = indicators.get("ema_12", [])
    ema_26 = indicators.get("ema_26", [])
    bb_upper, bb_middle, bb_lower = indicators.get("bollinger_bands", ([], [], []))
    latest_close = indicators.get("latest_close")
    previous_close = indicators.get("previous_close")

    if rsi_values:
        if rsi_values[-1] < 35:
            detected.append(("rsi_oversold", "BUY"))
        if rsi_values[-1] > 65:
            detected.append(("rsi_overbought", "SELL"))

    if len(macd_line) >= 2 and len(signal_line) >= 2:
        if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
            detected.append(("macd_crossover", "BUY"))
        if macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
            detected.append(("macd_crossover", "SELL"))

    if len(histogram) >= 4:
        if all(histogram[-idx] > histogram[-idx - 1] for idx in range(1, 4)) and histogram[-1] > 0:
            detected.append(("macd_momentum_rising", "BUY"))
        if all(histogram[-idx] < histogram[-idx - 1] for idx in range(1, 4)) and histogram[-1] < 0:
            detected.append(("macd_momentum_falling", "SELL"))

    if len(sma_short) >= 2 and len(sma_long) >= 2 and sma_long[-1] != 0:
        gap_pct = abs(sma_short[-1] - sma_long[-1]) / sma_long[-1] * 100
        if gap_pct < 1.0:
            approaching = sma_short[-1] > sma_short[-2] and sma_short[-1] < sma_long[-1]
            recent_golden_cross = sma_short[-1] > sma_long[-1] and sma_short[-2] <= sma_long[-2]
            if approaching or recent_golden_cross:
                detected.append(("sma_crossover_proximity", "BUY"))

    if volume_ratio and latest_close is not None and previous_close is not None and volume_ratio[-1] > 1.5:
        detected.append(("volume_breakout", "BUY" if latest_close > previous_close else "SELL"))

    if latest_close is not None and len(ema_12) >= 1 and len(ema_26) >= 1:
        if latest_close > ema_12[-1] > ema_26[-1]:
            detected.append(("ema_trend_bullish", "BUY"))
        if latest_close < ema_12[-1] < ema_26[-1]:
            detected.append(("ema_trend_bearish", "SELL"))

    if adx_values and adx_values[-1] > 25:
        detected.append(("adx_strong_trend", "BUY"))

    if bb_upper and bb_middle and bb_lower and latest_close is not None:
        if latest_close <= bb_lower[-1]:
            detected.append(("bb_lower_touch", "BUY"))
        if latest_close >= bb_upper[-1]:
            detected.append(("bb_upper_touch", "SELL"))

        if len(bb_upper) >= 50 and bb_middle[-1] != 0:
            current_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            widths = [
                (bb_upper[idx] - bb_lower[idx]) / bb_middle[idx]
                for idx in range(len(bb_upper) - 50, len(bb_upper))
                if bb_middle[idx] != 0
            ]
            if widths:
                pct_rank = sum(1 for width in widths if width > current_width) / len(widths)
                if pct_rank > 0.70:
                    detected.append(("bb_squeeze", "BUY"))

    return detected


def check_setup_families(
    symbol: str,
    indicators: dict[str, Any],
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    regime_result: RegimeResult,
) -> None:
    volume_24h = sum(close * volume for close, volume in zip(closes[-24:], volumes[-24:]))
    tradability_metrics = build_tradability_metrics(
        symbol=symbol,
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        volume_24h_usdt=volume_24h,
        indicators=indicators,
    )
    setups = detect_setups(indicators)
    if not setups:
        print("  No setup conditions detected from current indicators")
        return

    for setup_type, signal in setups:
        family = SETUP_TO_FAMILY.get(setup_type)
        validation = validate_setup_family(
            setup_type=setup_type,
            signal=signal,
            indicators=indicators,
            tradability_metrics=tradability_metrics,
            detailed_regime=regime_result.detailed_regime,
            exhaustion_score=regime_result.exhaustion_score,
        )
        if validation is None:
            print(f"  {setup_type:24s} [{signal}] no family validator")
            continue
        print(
            f"  {setup_type:24s} [{signal}] family={family.value if family else 'unknown'} "
            f"{tag(validation.passed)}"
        )
        print(
            f"    quality={validation.symbol_quality_score:.4f} "
            f"execution={validation.execution_quality_score:.4f} "
            f"room={validation.room_to_move_score:.4f} "
            f"entry_eligible={validation.entry_eligible}"
        )
        if validation.rejection_reason:
            print(f"    rejection={validation.rejection_reason}")


def determine_verdict(
    symbol: str,
    stage1_passed: bool,
    stage2_components: dict[str, float],
    stage3_result: TradabilityResult,
    universe_reference: UniverseReference | None,
    composite_result: CompositeScoreResult,
    detected_setups: list[tuple[str, str]],
) -> str:
    if not stage1_passed:
        return "BLOCKED at Stage 1 hard filters"

    if not stage3_result.passed:
        return f"BLOCKED at Stage 3 tradability ({stage3_result.reason_text})"

    if universe_reference is not None:
        if symbol not in universe_reference.selected_symbols:
            rank = universe_reference.rank_for(symbol)
            cutoff = universe_reference.cutoff_score
            if rank is None:
                return "BLOCKED before Stage 2 ranking because the symbol never entered the ranked tradable set"
            return (
                f"BLOCKED at Stage 2 activity ranking "
                f"(rank {rank}/{universe_reference.ranked_count}, score {stage2_components['composite']:.4f}"
                f", cutoff {cutoff:.4f})"
            )
    elif stage2_components["composite"] < 0.25:
        return f"LIKELY blocked at Stage 2 activity ranking (score {stage2_components['composite']:.4f})"

    if composite_result.signal == "HOLD":
        if detected_setups:
            return (
                "PASSED filters but composite/strategy layer held "
                f"({', '.join(composite_result.reject_reason_codes) if composite_result.reject_reason_codes else 'no composite trigger'})"
            )
        return "PASSED filters but no setup family or strategy signal fired"

    return "PASSED filters and a live entry signal exists now"


async def diagnose_coin(target: dict[str, Any], universe_reference: UniverseReference | None) -> str:
    symbol = target["symbol"]
    print(f"\n{SEP}")
    print(f"  DIAGNOSTIC REPORT: {symbol} (move +{target['move_pct']}%, price ${target['price']})")
    print(SEP)

    print("\n--- STAGE 1: HARD FILTERS ---")
    stage1_passed, ticker_data = await check_hard_filters(symbol, universe_reference)
    if not ticker_data:
        verdict = "BLOCKED at Stage 1 because symbol data could not be fetched"
        print(f"\nVERDICT: {verdict}")
        return f"{symbol}: {verdict}"

    print("\n--- FETCHING CANDLE DATA ---")
    candles = await fetch_candles(symbol=symbol, interval="1h", limit=200)
    print(f"  Loaded {len(candles)} candles")
    if len(candles) < 50:
        verdict = f"BLOCKED because only {len(candles)} candles were available"
        print(f"\nVERDICT: {verdict}")
        return f"{symbol}: {verdict}"

    store = DataStore.get_instance()
    store.set_candles(symbol, "1h", candles)
    closes, highs, lows, volumes = split_candles(candles)

    print("\n--- STAGE 2: ACTIVITY RANKING ---")
    stage2_components = check_activity_ranking(
        symbol,
        ticker_data["volume_24h"],
        closes[-1],
        store,
        universe_reference,
    )

    print("\n--- STAGE 3: TRADABILITY EVALUATION ---")
    stage3_result = check_tradability(
        symbol,
        closes,
        highs,
        lows,
        volumes,
        ticker_data["volume_24h"],
    )

    print("\n--- STAGE 4: TECHNICAL INDICATORS ---")
    indicators = compute_indicators(
        closes,
        config=INDICATOR_CONFIG,
        highs=highs,
        lows=lows,
        volumes=volumes,
    )
    indicators["symbol"] = symbol
    indicators["market_quality_score"] = stage3_result.metrics.market_quality_score
    print_indicators(indicators)

    print("\n--- STAGE 5: REGIME CLASSIFICATION ---")
    regime_result = check_regime(indicators)

    print("\n--- STAGE 7: COMPOSITE SCORE DETAIL ---")
    composite_result = check_composite(indicators, regime_result, stage3_result)

    print("\n--- STAGE 6: STRATEGY SIGNAL DETECTION ---")
    check_strategies(indicators, composite_result)

    print("\n--- STAGE 8: SETUP FAMILY DETECTION ---")
    detected_setups = detect_setups(indicators)
    check_setup_families(symbol, indicators, closes, highs, lows, volumes, regime_result)

    verdict = determine_verdict(
        symbol,
        stage1_passed,
        stage2_components,
        stage3_result,
        universe_reference,
        composite_result,
        detected_setups,
    )
    print(f"\nVERDICT: {verdict}")
    return f"{symbol}: {verdict}"


async def main() -> None:
    print(f"\n{SEP}")
    print("  MISSED COIN DIAGNOSTIC")
    print(SEP)

    reset_runtime_state()
    store = DataStore.get_instance()

    print("\nPriming BTCUSDT reference candles for relative strength...")
    btc_candles = await fetch_candles(symbol="BTCUSDT", interval="1h", limit=200)
    store.set_candles("BTCUSDT", "1h", btc_candles)
    print(f"  BTCUSDT loaded: {len(btc_candles)} candles")

    print("\nRefreshing dynamic universe snapshot for an exact Stage 2 cutoff...")
    universe_reference = await build_universe_reference()
    print(
        f"  Candidate pool: {universe_reference.candidate_count} symbols, "
        f"ranked tradable set: {universe_reference.ranked_count}, "
        f"top-{SETTINGS.dynamic_universe_size} cutoff: "
        f"{fmt_optional(universe_reference.cutoff_score, 4)}"
    )

    verdicts: list[str] = []
    for target in TARGETS:
        verdicts.append(await diagnose_coin(target, universe_reference))

    print(f"\n{SEP}")
    print("  SUMMARY")
    print(SEP)
    for verdict in verdicts:
        print(f"  - {verdict}")


if __name__ == "__main__":
    asyncio.run(main())
