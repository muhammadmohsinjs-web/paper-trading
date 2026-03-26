"""Shared tradability and movement-quality evaluation helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.engine.fee_model import SPOT_FEE_RATE
from app.engine.slippage import estimate_slippage_rate
from app.market.indicators import compute_indicators

SETTINGS = get_settings()

STABLECOIN_BASE_DENYLIST = {
    "USDC",
    "USDT",
    "BUSD",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "USD1",
    "USDE",
    "USDD",
    "PYUSD",
    "FRAX",
}


@dataclass(frozen=True)
class TradabilityMetrics:
    atr_pct_14: float = 0.0
    range_pct_20: float = 0.0
    range_pct_24h: float = 0.0
    abs_change_pct_24h: float = 0.0
    directional_displacement_pct_10: float = 0.0
    ema_spread_pct: float = 0.0
    short_sma_slope_pct_3: float = 0.0
    close_vs_close_5_pct: float = 0.0
    volume_ratio: float = 0.0
    bb_width_pct: float = 0.0
    market_quality_score: float = 0.0
    volume_24h_usdt: float = 0.0
    estimated_tp_pct_from_atr: float = 0.0
    total_round_trip_cost_pct: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class TradabilityResult:
    passed: bool
    reason_codes: list[str]
    reason_text: str
    metrics: TradabilityMetrics
    market_quality_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason_codes": list(self.reason_codes),
            "reason_text": self.reason_text,
            "metrics": self.metrics.to_dict(),
            "market_quality_score": self.market_quality_score,
        }


@dataclass(frozen=True)
class MovementQuality:
    passed: bool
    score: float
    reason_code: str | None
    reason_text: str
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "metrics": dict(self.metrics),
        }


def infer_base_asset(symbol: str, quote_asset: str = "USDT") -> str:
    normalized = (symbol or "").upper()
    suffix = quote_asset.upper()
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized


def _pct_change(newer: float, older: float) -> float:
    if older <= 0:
        return 0.0
    return (newer - older) / older * 100.0


def _range_pct(values: list[float]) -> float:
    if not values:
        return 0.0
    high = max(values)
    low = min(values)
    midpoint = (high + low) / 2.0
    if midpoint <= 0:
        return 0.0
    return (high - low) / midpoint * 100.0


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _score_min_threshold(value: float, minimum: float, target: float) -> float:
    if value <= minimum:
        return 0.0
    if value >= target:
        return 1.0
    return _clamp01((value - minimum) / max(target - minimum, 1e-9))


def build_tradability_metrics(
    *,
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    volume_24h_usdt: float,
    config: dict[str, Any] | None = None,
    indicators: dict[str, Any] | None = None,
    estimated_notional: Decimal | None = None,
) -> TradabilityMetrics:
    derived = indicators or compute_indicators(closes, config or {}, highs=highs, lows=lows, volumes=volumes)
    latest_close = closes[-1] if closes else 0.0
    atr_values = derived.get("atr", [])
    latest_atr = float(atr_values[-1]) if atr_values else 0.0
    atr_pct_14 = (latest_atr / latest_close * 100.0) if latest_close > 0 else 0.0

    range_pct_20 = _range_pct(closes[-20:])
    range_pct_24h = _range_pct(closes[-24:])

    if len(closes) >= 25:
        abs_change_pct_24h = abs(_pct_change(closes[-1], closes[-25]))
    elif len(closes) >= 2:
        abs_change_pct_24h = abs(_pct_change(closes[-1], closes[0]))
    else:
        abs_change_pct_24h = 0.0

    if len(closes) >= 11:
        directional_displacement_pct_10 = _pct_change(closes[-1], closes[-11])
    elif len(closes) >= 2:
        directional_displacement_pct_10 = _pct_change(closes[-1], closes[0])
    else:
        directional_displacement_pct_10 = 0.0

    ema_12 = derived.get("ema_12", [])
    ema_26 = derived.get("ema_26", [])
    ema_spread_pct = 0.0
    if ema_12 and ema_26 and float(ema_26[-1]) != 0.0:
        ema_spread_pct = (float(ema_12[-1]) - float(ema_26[-1])) / float(ema_26[-1]) * 100.0

    sma_short = derived.get("sma_short", [])
    short_sma_slope_pct_3 = 0.0
    if len(sma_short) >= 4 and float(sma_short[-4]) != 0.0:
        short_sma_slope_pct_3 = (float(sma_short[-1]) - float(sma_short[-4])) / float(sma_short[-4]) * 100.0

    close_vs_close_5_pct = 0.0
    if len(closes) >= 6 and closes[-6] != 0.0:
        close_vs_close_5_pct = (closes[-1] - closes[-6]) / closes[-6] * 100.0

    volume_ratio_values = derived.get("volume_ratio", [])
    volume_ratio = float(volume_ratio_values[-1]) if volume_ratio_values else 0.0

    bb_upper, bb_middle, bb_lower = derived.get("bollinger_bands", ([], [], []))
    bb_width_pct = 0.0
    if bb_upper and bb_middle and bb_lower and float(bb_middle[-1]) != 0.0:
        bb_width_pct = (float(bb_upper[-1]) - float(bb_lower[-1])) / float(bb_middle[-1]) * 100.0

    liquidity_floor = max(
        float(SETTINGS.universe_min_24h_volume_usdt),
        float(SETTINGS.multi_coin_liquidity_floor_usdt),
    )
    liquidity_score = _score_min_threshold(volume_24h_usdt, liquidity_floor * 0.5, liquidity_floor * 2.0)
    atr_score = _score_min_threshold(atr_pct_14, 0.20, 0.80)
    range_score = _score_min_threshold(range_pct_24h, 0.60, 1.50)
    change_score = _score_min_threshold(abs_change_pct_24h, 0.35, 1.20)
    market_quality_score = round(
        0.30 * atr_score
        + 0.25 * range_score
        + 0.20 * change_score
        + 0.15 * liquidity_score
        + 0.10 * _score_min_threshold(volume_ratio, 0.80, 1.40),
        4,
    )

    atr_multiplier = float((config or {}).get("atr_stop_multiplier", 2.0))
    take_profit_ratio = float((config or {}).get("take_profit_ratio", 2.0))
    estimated_tp_pct_from_atr = max(0.0, atr_pct_14 * atr_multiplier * take_profit_ratio)

    notional = estimated_notional if estimated_notional is not None else Decimal("1000")
    fee_rate = Decimal(str((config or {}).get("spot_fee_rate", SETTINGS.spot_fee_rate)))
    total_round_trip_cost_pct = float(
        (fee_rate * Decimal("2") + estimate_slippage_rate(notional) * Decimal("2")) * Decimal("100")
    )

    return TradabilityMetrics(
        atr_pct_14=round(atr_pct_14, 4),
        range_pct_20=round(range_pct_20, 4),
        range_pct_24h=round(range_pct_24h, 4),
        abs_change_pct_24h=round(abs_change_pct_24h, 4),
        directional_displacement_pct_10=round(directional_displacement_pct_10, 4),
        ema_spread_pct=round(ema_spread_pct, 4),
        short_sma_slope_pct_3=round(short_sma_slope_pct_3, 4),
        close_vs_close_5_pct=round(close_vs_close_5_pct, 4),
        volume_ratio=round(volume_ratio, 4),
        bb_width_pct=round(bb_width_pct, 4),
        market_quality_score=market_quality_score,
        volume_24h_usdt=round(volume_24h_usdt, 2),
        estimated_tp_pct_from_atr=round(estimated_tp_pct_from_atr, 4),
        total_round_trip_cost_pct=round(total_round_trip_cost_pct, 4),
    )


def evaluate_symbol_tradability(
    *,
    symbol: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    volume_24h_usdt: float,
    config: dict[str, Any] | None = None,
    indicators: dict[str, Any] | None = None,
    estimated_notional: Decimal | None = None,
) -> TradabilityResult:
    metrics = build_tradability_metrics(
        symbol=symbol,
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        volume_24h_usdt=volume_24h_usdt,
        config=config,
        indicators=indicators,
        estimated_notional=estimated_notional,
    )
    reason_codes: list[str] = []

    if infer_base_asset(symbol) in STABLECOIN_BASE_DENYLIST:
        reason_codes.append("DENYLIST_STABLE_BASE")

    low_vol_flags = 0
    if metrics.atr_pct_14 < 0.20:
        reason_codes.append("ATR_PCT_TOO_LOW")
        low_vol_flags += 1
    if metrics.range_pct_24h < 0.60:
        reason_codes.append("RANGE_PCT_TOO_LOW")
        low_vol_flags += 1
    if metrics.abs_change_pct_24h < 0.35:
        reason_codes.append("ABS_CHANGE_TOO_LOW")
        low_vol_flags += 1
    if low_vol_flags >= 2:
        reason_codes.append("NEAR_PEG_PROFILE")

    liquidity_floor = max(
        float(SETTINGS.universe_min_24h_volume_usdt),
        float(SETTINGS.multi_coin_liquidity_floor_usdt),
    )
    if metrics.volume_24h_usdt < liquidity_floor:
        reason_codes.append("LIQUIDITY_TOO_LOW")
    if metrics.market_quality_score < 0.45:
        reason_codes.append("MARKET_QUALITY_TOO_LOW")
    if metrics.estimated_tp_pct_from_atr < metrics.total_round_trip_cost_pct * 1.5:
        reason_codes.append("MOVE_BELOW_COST")

    deduped = list(dict.fromkeys(reason_codes))
    return TradabilityResult(
        passed=not deduped,
        reason_codes=deduped,
        reason_text="; ".join(deduped) if deduped else "Symbol passed tradability checks",
        metrics=metrics,
        market_quality_score=metrics.market_quality_score,
    )


def evaluate_movement_quality(
    *,
    direction: str,
    metrics: TradabilityMetrics,
    require_volume: bool = True,
) -> MovementQuality:
    directional_move = metrics.directional_displacement_pct_10 if direction == "BUY" else -metrics.directional_displacement_pct_10
    failures: list[tuple[str, str]] = []

    if metrics.atr_pct_14 < 0.25:
        failures.append(("SETUP_NO_ABSOLUTE_EXPANSION", "ATR floor not met"))
    if metrics.range_pct_20 < 0.80:
        failures.append(("SETUP_RANGE_TOO_SMALL", "20-candle range is too compressed"))
    if directional_move < 0.30:
        failures.append(("SETUP_NO_ABSOLUTE_EXPANSION", "Directional displacement is too weak"))
    if require_volume and metrics.volume_ratio < 0.80:
        failures.append(("SETUP_VOLUME_UNCONFIRMED", "Volume ratio is below confirmation floor"))

    atr_score = _score_min_threshold(metrics.atr_pct_14, 0.25, 0.90)
    range_score = _score_min_threshold(metrics.range_pct_20, 0.80, 1.80)
    move_score = _score_min_threshold(directional_move, 0.30, 0.90)
    volume_score = 1.0 if not require_volume else _score_min_threshold(metrics.volume_ratio, 0.80, 1.50)
    score = round(0.30 * atr_score + 0.25 * range_score + 0.25 * move_score + 0.20 * volume_score, 4)

    reason_code = failures[0][0] if failures else None
    reason_text = failures[0][1] if failures else "Movement quality passed"
    return MovementQuality(
        passed=not failures,
        score=score,
        reason_code=reason_code,
        reason_text=reason_text,
        metrics={
            "atr_pct_14": metrics.atr_pct_14,
            "range_pct_20": metrics.range_pct_20,
            "directional_displacement_pct_10": round(directional_move, 4),
            "volume_ratio": metrics.volume_ratio,
            "ema_spread_pct": metrics.ema_spread_pct,
            "short_sma_slope_pct_3": metrics.short_sma_slope_pct_3,
            "close_vs_close_5_pct": metrics.close_vs_close_5_pct,
            "bb_width_pct": metrics.bb_width_pct,
        },
    )


def default_fee_rate(config: dict[str, Any] | None = None) -> Decimal:
    value = (config or {}).get("spot_fee_rate", SETTINGS.spot_fee_rate)
    return Decimal(str(value)) if value is not None else SPOT_FEE_RATE
