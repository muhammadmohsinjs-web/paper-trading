"""Opportunity scanner — scans multiple symbols for trading setups."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.regime.classifier import RegimeClassifier
from app.regime.types import MarketRegime
from app.risk.portfolio import get_correlation
from app.scanner.relative_strength import get_relative_strength
from app.scanner.types import RankedSetup, RankedSymbol, ScanResult
from app.selector.selector import REGIME_AFFINITY

logger = logging.getLogger(__name__)
settings = get_settings()

# Default symbols to scan (top by volume on Binance)
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
    "APTUSDT", "OPUSDT", "ARBUSDT", "SUIUSDT", "SEIUSDT",
    "INJUSDT", "TIAUSDT", "FETUSDT", "RNDRUSDT", "WIFUSDT",
    "JUPUSDT", "STXUSDT", "IMXUSDT", "RUNEUSDT", "ARUSDT",
    "PENDLEUSDT", "ONDOUSDT", "FILUSDT", "ENAUSDT", "WLDUSDT",
]

MIN_SETUP_SCORE = 0.20  # Lowered from 0.3 to catch moderate opportunities
MIN_CANDLES_FOR_SCAN = 50


class OpportunityScanner:
    """Scans multiple symbols for trading setups and ranks them."""

    def __init__(self, symbols: list[str] | None = None):
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.regime_classifier = RegimeClassifier()

    def scan(
        self,
        interval: str = "1h",
        max_results: int = 5,
    ) -> ScanResult:
        """Scan all configured symbols for trading opportunities.

        Reads from the DataStore (must have data for each symbol).
        Returns ranked setups sorted by score.
        """
        store = DataStore.get_instance()
        opportunities: list[RankedSetup] = []
        symbols_with_data = 0
        symbols_no_data: list[str] = []
        symbols_no_setup: list[str] = []
        overall_regime = "unknown"

        for symbol in self.symbols:
            candles = store.get_candles(symbol, interval, 200)
            if len(candles) < MIN_CANDLES_FOR_SCAN:
                symbols_no_data.append(f"{symbol}({len(candles)})")
                continue

            symbols_with_data += 1
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            volumes = [c.volume for c in candles]

            indicators = compute_indicators(
                closes, highs=highs, lows=lows, volumes=volumes
            )

            # Detect regime
            regime_result = self.regime_classifier.classify(indicators)
            if symbol == "BTCUSDT":
                overall_regime = regime_result.regime.value

            # Detect setups
            setups = self._detect_setups(symbol, indicators, regime_result.regime, closes=closes)
            if not setups:
                symbols_no_setup.append(symbol)
            opportunities.extend(setups)

        if symbols_no_data:
            logger.warning(
                "scanner: %d/%d symbols skipped (insufficient data): %s",
                len(symbols_no_data), len(self.symbols),
                ", ".join(symbols_no_data[:10]),
            )
        if symbols_no_setup:
            logger.info(
                "scanner: %d symbols had data but no setup detected: %s",
                len(symbols_no_setup), ", ".join(symbols_no_setup[:10]),
            )
        logger.info(
            "scanner: %d symbols scanned, %d setups found, regime=%s",
            symbols_with_data, len(opportunities), overall_regime,
        )

        # Sort by score descending
        opportunities.sort(key=lambda s: s.score, reverse=True)

        return ScanResult(
            scanned_at=datetime.now(timezone.utc).isoformat(),
            symbols_scanned=symbols_with_data,
            regime=overall_regime,
            opportunities=opportunities[:max_results],
        )

    def rank_symbols(
        self,
        interval: str = "1h",
        max_results: int = 5,
        *,
        liquidity_floor_usdt: float | None = None,
    ) -> list[RankedSymbol]:
        """Return one ranked candidate per symbol with diversification-aware ordering."""
        store = DataStore.get_instance()
        candidates: list[RankedSymbol] = []
        min_liquidity = float(
            liquidity_floor_usdt
            if liquidity_floor_usdt is not None
            else settings.multi_coin_liquidity_floor_usdt
        )

        skipped_data: list[str] = []
        skipped_setup: list[str] = []
        skipped_liquidity: list[str] = []

        for symbol in self.symbols:
            candles = store.get_candles(symbol, interval, 200)
            if len(candles) < MIN_CANDLES_FOR_SCAN:
                skipped_data.append(f"{symbol}({len(candles)})")
                continue

            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            volumes = [c.volume for c in candles]
            indicators = compute_indicators(closes, highs=highs, lows=lows, volumes=volumes)
            regime_result = self.regime_classifier.classify(indicators)
            setups = self._detect_setups(symbol, indicators, regime_result.regime, closes=closes)
            if not setups:
                skipped_setup.append(symbol)
                continue

            liquidity_usdt = self._estimate_liquidity_usdt(candles)
            if liquidity_usdt < min_liquidity:
                skipped_liquidity.append(f"{symbol}(${liquidity_usdt:,.0f})")
                continue

            best_setup = max(setups, key=lambda setup: setup.score)
            regime_affinity = REGIME_AFFINITY.get(regime_result.regime, {}).get(
                best_setup.recommended_strategy,
                0.5,
            )
            liquidity_score = min(liquidity_usdt / max(min_liquidity * 4.0, 1.0), 1.0)
            final_score = (
                best_setup.score * 0.75
                + regime_affinity * 0.15
                + liquidity_score * 0.10
            )
            candidates.append(
                RankedSymbol(
                    symbol=symbol,
                    score=final_score,
                    regime=regime_result.regime.value,
                    setup_type=best_setup.setup_type,
                    recommended_strategy=best_setup.recommended_strategy,
                    reason=best_setup.reason,
                    liquidity_usdt=liquidity_usdt,
                    indicators=best_setup.indicators,
                )
            )

        if skipped_data:
            logger.warning(
                "rank_symbols: %d symbols skipped (no data): %s",
                len(skipped_data), ", ".join(skipped_data[:10]),
            )
        if skipped_setup:
            logger.info(
                "rank_symbols: %d symbols skipped (no setup): %s",
                len(skipped_setup), ", ".join(skipped_setup[:10]),
            )
        if skipped_liquidity:
            logger.info(
                "rank_symbols: %d symbols skipped (low liquidity, floor=$%s): %s",
                len(skipped_liquidity), f"{min_liquidity:,.0f}",
                ", ".join(skipped_liquidity[:10]),
            )
        logger.info(
            "rank_symbols: %d candidates from %d symbols scanned",
            len(candidates), len(self.symbols),
        )

        candidates.sort(key=lambda item: item.score, reverse=True)

        selected: list[RankedSymbol] = []
        remaining = candidates[:]
        while remaining and len(selected) < max_results:
            best_idx = 0
            best_score = -1.0
            for idx, candidate in enumerate(remaining):
                adjusted_score = candidate.score
                if selected:
                    max_corr = max(get_correlation(candidate.symbol, chosen.symbol) for chosen in selected)
                    adjusted_score *= max(0.25, 1.0 - (0.35 * max_corr))
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_idx = idx

            selected_candidate = remaining.pop(best_idx)
            selected.append(
                RankedSymbol(
                    symbol=selected_candidate.symbol,
                    score=round(best_score, 4),
                    regime=selected_candidate.regime,
                    setup_type=selected_candidate.setup_type,
                    recommended_strategy=selected_candidate.recommended_strategy,
                    reason=selected_candidate.reason,
                    liquidity_usdt=selected_candidate.liquidity_usdt,
                    indicators=selected_candidate.indicators,
                )
            )

        return selected

    def _detect_setups(
        self,
        symbol: str,
        indicators: dict[str, Any],
        regime: MarketRegime,
        closes: list[float] | None = None,
    ) -> list[RankedSetup]:
        """Detect trading setups for a single symbol.

        Checks 12 setup types covering extreme, moderate, and trend conditions
        so the scanner can find opportunities in any market environment.
        """
        setups: list[RankedSetup] = []

        # Extract indicator values
        rsi_values = indicators.get("rsi", [])
        latest_rsi = rsi_values[-1] if rsi_values else None

        bb = indicators.get("bollinger_bands", ([], [], []))
        bb_upper, bb_middle, bb_lower = bb if len(bb) == 3 else ([], [], [])

        volume_ratio_values = indicators.get("volume_ratio", [])
        latest_volume_ratio = volume_ratio_values[-1] if volume_ratio_values else None

        sma_short = indicators.get("sma_short", [])
        sma_long = indicators.get("sma_long", [])

        latest_close = indicators.get("latest_close")
        previous_close = indicators.get("previous_close")

        macd_data = indicators.get("macd", ([], [], []))
        macd_line, macd_signal, macd_hist = (
            macd_data if isinstance(macd_data, tuple) and len(macd_data) == 3
            else ([], [], [])
        )

        adx_values = indicators.get("adx", [])
        latest_adx = adx_values[-1] if adx_values else None

        ema_12 = indicators.get("ema_12", [])
        ema_26 = indicators.get("ema_26", [])

        atr_values = indicators.get("atr", [])

        # ── Setup 1: RSI Oversold (relaxed from <30 to <35) ──
        if latest_rsi is not None and latest_rsi < 35:
            strength = max(0, (35 - latest_rsi) / 35)
            regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(strength, regime_align, vol_confirm, 0.5, symbol)
            if score >= MIN_SETUP_SCORE:
                setups.append(RankedSetup(
                    symbol=symbol,
                    score=score,
                    setup_type="rsi_oversold",
                    signal="BUY",
                    regime=regime.value,
                    recommended_strategy="rsi_mean_reversion",
                    reason=f"RSI oversold at {latest_rsi:.1f}",
                    indicators={"rsi": round(latest_rsi, 2), "volume_ratio": round(latest_volume_ratio or 0, 2)},
                ))

        # ── Setup 2: RSI Overbought (relaxed from >70 to >65) ──
        if latest_rsi is not None and latest_rsi > 65:
            strength = max(0, (latest_rsi - 65) / 35)
            regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(strength, regime_align, vol_confirm, 0.5, symbol)
            if score >= MIN_SETUP_SCORE:
                setups.append(RankedSetup(
                    symbol=symbol,
                    score=score,
                    setup_type="rsi_overbought",
                    signal="SELL",
                    regime=regime.value,
                    recommended_strategy="rsi_mean_reversion",
                    reason=f"RSI overbought at {latest_rsi:.1f}",
                    indicators={"rsi": round(latest_rsi, 2)},
                ))

        # ── Setup 3: Bollinger Band squeeze (relaxed from 80% to 70%) ──
        if bb_upper and bb_middle and bb_lower and bb_middle[-1] != 0:
            current_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            if len(bb_upper) >= 50:
                widths = [
                    (bb_upper[i] - bb_lower[i]) / bb_middle[i]
                    for i in range(max(0, len(bb_upper) - 50), len(bb_upper))
                    if bb_middle[i] != 0
                ]
                pct_rank = sum(1 for w in widths if w > current_width) / len(widths)
                if pct_rank > 0.70:  # Current width is in lowest 30%
                    strength = pct_rank
                    vol_confirm = min(latest_volume_ratio / 1.2, 1.0) if latest_volume_ratio and latest_volume_ratio > 1.2 else 0.4
                    score = self._setup_score(strength, 0.7, vol_confirm, 0.6, symbol)
                    if score >= MIN_SETUP_SCORE:
                        setups.append(RankedSetup(
                            symbol=symbol,
                            score=score,
                            setup_type="bb_squeeze",
                            signal="BUY",
                            regime=regime.value,
                            recommended_strategy="bollinger_bounce",
                            reason=f"BB squeeze detected (width percentile: {(1-pct_rank)*100:.0f}%)",
                            indicators={"bb_width": round(current_width, 4), "width_percentile": round((1-pct_rank)*100, 1)},
                        ))

        # ── Setup 4: SMA crossover proximity (relaxed from 0.5% to 1.0%) ──
        if len(sma_short) >= 2 and len(sma_long) >= 2:
            gap_pct = abs(sma_short[-1] - sma_long[-1]) / sma_long[-1] * 100 if sma_long[-1] != 0 else 999
            if gap_pct < 1.0:
                approaching_golden = sma_short[-1] > sma_short[-2] and sma_short[-1] < sma_long[-1]
                recent_golden_cross = sma_short[-1] > sma_long[-1] and sma_short[-2] <= sma_long[-2]
                if approaching_golden or recent_golden_cross:
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    trend_align = 1.0 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.4
                    strength = 0.8 if recent_golden_cross else 0.6
                    score = self._setup_score(strength, trend_align, vol_confirm, 0.6, symbol)
                    if score >= MIN_SETUP_SCORE:
                        reason = "SMA golden cross just occurred" if recent_golden_cross else f"SMA approaching golden cross (gap: {gap_pct:.2f}%)"
                        setups.append(RankedSetup(
                            symbol=symbol,
                            score=score,
                            setup_type="sma_crossover_proximity",
                            signal="BUY",
                            regime=regime.value,
                            recommended_strategy="sma_crossover",
                            reason=reason,
                            indicators={"sma_gap_pct": round(gap_pct, 3)},
                        ))

        # ── Setup 5: Volume breakout (relaxed from >2.0 to >1.5) ──
        if latest_volume_ratio is not None and latest_volume_ratio > 1.5:
            if latest_close and previous_close:
                price_up = latest_close > previous_close
                strength = min((latest_volume_ratio - 1.5) / 2.5, 1.0)
                trend_align = 1.0 if regime in (MarketRegime.TRENDING_UP,) and price_up else 0.5
                score = self._setup_score(strength, trend_align, 1.0, 0.7, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="volume_breakout",
                        signal="BUY" if price_up else "SELL",
                        regime=regime.value,
                        recommended_strategy="macd_momentum",
                        reason=f"Volume breakout ({latest_volume_ratio:.1f}x avg) with price {'up' if price_up else 'down'}",
                        indicators={"volume_ratio": round(latest_volume_ratio, 2)},
                    ))

        # ── Setup 6: MACD bullish crossover ──
        if len(macd_line) >= 2 and len(macd_signal) >= 2:
            macd_cross_up = macd_line[-1] > macd_signal[-1] and macd_line[-2] <= macd_signal[-2]
            macd_cross_down = macd_line[-1] < macd_signal[-1] and macd_line[-2] >= macd_signal[-2]
            if macd_cross_up or macd_cross_down:
                signal = "BUY" if macd_cross_up else "SELL"
                hist_val = macd_hist[-1] if macd_hist else 0
                strength = min(abs(hist_val) / (abs(macd_signal[-1]) + 1e-9), 1.0) * 0.7
                regime_align = 0.8 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.5
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.4), regime_align, vol_confirm, 0.6, symbol)
                if score >= MIN_SETUP_SCORE:
                    direction = "bullish" if macd_cross_up else "bearish"
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="macd_crossover",
                        signal=signal,
                        regime=regime.value,
                        recommended_strategy="macd_momentum",
                        reason=f"MACD {direction} crossover (hist: {hist_val:.4f})",
                        indicators={
                            "macd": round(macd_line[-1], 4),
                            "macd_signal": round(macd_signal[-1], 4),
                            "macd_hist": round(hist_val, 4),
                        },
                    ))

        # ── Setup 7: MACD histogram momentum (growing for 3+ bars) ──
        if len(macd_hist) >= 4:
            hist_growing = all(macd_hist[-i] > macd_hist[-i - 1] for i in range(1, 4))
            hist_shrinking = all(macd_hist[-i] < macd_hist[-i - 1] for i in range(1, 4))
            if hist_growing and macd_hist[-1] > 0:
                strength = min(abs(macd_hist[-1]) * 100, 1.0) * 0.6
                score = self._setup_score(max(strength, 0.35), 0.7, 0.6, 0.7, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="macd_momentum_rising",
                        signal="BUY",
                        regime=regime.value,
                        recommended_strategy="macd_momentum",
                        reason=f"MACD histogram rising for 3+ bars ({macd_hist[-1]:.4f})",
                        indicators={"macd_hist": round(macd_hist[-1], 4)},
                    ))
            elif hist_shrinking and macd_hist[-1] < 0:
                strength = min(abs(macd_hist[-1]) * 100, 1.0) * 0.6
                score = self._setup_score(max(strength, 0.35), 0.7, 0.6, 0.7, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="macd_momentum_falling",
                        signal="SELL",
                        regime=regime.value,
                        recommended_strategy="macd_momentum",
                        reason=f"MACD histogram falling for 3+ bars ({macd_hist[-1]:.4f})",
                        indicators={"macd_hist": round(macd_hist[-1], 4)},
                    ))

        # ── Setup 8: EMA trend alignment (price > EMA12 > EMA26 = strong uptrend) ──
        if latest_close and len(ema_12) >= 2 and len(ema_26) >= 2:
            bullish_stack = latest_close > ema_12[-1] > ema_26[-1]
            bearish_stack = latest_close < ema_12[-1] < ema_26[-1]
            if bullish_stack:
                ema_spread = (ema_12[-1] - ema_26[-1]) / ema_26[-1] * 100
                strength = min(ema_spread / 3.0, 1.0)  # 3% spread = max strength
                # Bonus for widening spread (momentum increasing)
                prev_spread = (ema_12[-2] - ema_26[-2]) / ema_26[-2] * 100 if ema_26[-2] != 0 else 0
                widening = ema_spread > prev_spread
                trend_align = 0.9 if regime == MarketRegime.TRENDING_UP else 0.5
                vol_confirm = min(latest_volume_ratio / 0.8, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.3), trend_align, vol_confirm, 0.8, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="ema_trend_bullish",
                        signal="BUY",
                        regime=regime.value,
                        recommended_strategy="sma_crossover",
                        reason=f"Bullish EMA stack (spread: {ema_spread:.2f}%, {'widening' if widening else 'steady'})",
                        indicators={"ema_spread_pct": round(ema_spread, 3), "widening": widening},
                    ))
            elif bearish_stack:
                ema_spread = (ema_26[-1] - ema_12[-1]) / ema_26[-1] * 100
                strength = min(ema_spread / 3.0, 1.0)
                trend_align = 0.9 if regime == MarketRegime.TRENDING_DOWN else 0.5
                vol_confirm = min(latest_volume_ratio / 0.8, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.3), trend_align, vol_confirm, 0.8, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="ema_trend_bearish",
                        signal="SELL",
                        regime=regime.value,
                        recommended_strategy="sma_crossover",
                        reason=f"Bearish EMA stack (spread: {ema_spread:.2f}%)",
                        indicators={"ema_spread_pct": round(ema_spread, 3)},
                    ))

        # ── Setup 9: ADX strong trend ──
        if latest_adx is not None and latest_adx > 25:
            # ADX > 25 = strong trend. Determine direction from EMA or SMA
            if len(ema_12) >= 1 and len(ema_26) >= 1:
                trend_up = ema_12[-1] > ema_26[-1]
                signal = "BUY" if trend_up else "SELL"
                strength = min((latest_adx - 25) / 25, 1.0)  # ADX 50 = max strength
                regime_align = 0.9 if regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN) else 0.5
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.35), regime_align, vol_confirm, 0.8, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="adx_strong_trend",
                        signal=signal,
                        regime=regime.value,
                        recommended_strategy="macd_momentum" if trend_up else "rsi_mean_reversion",
                        reason=f"ADX strong trend at {latest_adx:.1f} ({'bullish' if trend_up else 'bearish'})",
                        indicators={"adx": round(latest_adx, 2)},
                    ))

        # ── Setup 10: Bollinger Band mean reversion (price touching lower/upper band) ──
        if bb_upper and bb_lower and latest_close and bb_middle:
            bb_width = bb_upper[-1] - bb_lower[-1]
            if bb_width > 0:
                # %B: 0 = at lower band, 1 = at upper band
                pct_b = (latest_close - bb_lower[-1]) / bb_width
                if pct_b <= 0.05:  # Price at or below lower band
                    strength = max(0, (0.1 - pct_b) / 0.1) * 0.8
                    regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    score = self._setup_score(max(strength, 0.4), regime_align, vol_confirm, 0.5, symbol)
                    if score >= MIN_SETUP_SCORE:
                        setups.append(RankedSetup(
                            symbol=symbol,
                            score=score,
                            setup_type="bb_lower_touch",
                            signal="BUY",
                            regime=regime.value,
                            recommended_strategy="bollinger_bounce",
                            reason=f"Price touching lower BB (%B: {pct_b:.2f})",
                            indicators={"pct_b": round(pct_b, 3), "bb_width": round(bb_width, 4)},
                        ))
                elif pct_b >= 0.95:  # Price at or above upper band
                    strength = max(0, (pct_b - 0.9) / 0.1) * 0.8
                    regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    score = self._setup_score(max(strength, 0.4), regime_align, vol_confirm, 0.5, symbol)
                    if score >= MIN_SETUP_SCORE:
                        setups.append(RankedSetup(
                            symbol=symbol,
                            score=score,
                            setup_type="bb_upper_touch",
                            signal="SELL",
                            regime=regime.value,
                            recommended_strategy="bollinger_bounce",
                            reason=f"Price touching upper BB (%B: {pct_b:.2f})",
                            indicators={"pct_b": round(pct_b, 3), "bb_width": round(bb_width, 4)},
                        ))

        # ── Setup 11: RSI divergence (bullish/bearish) ──
        rsi_div = indicators.get("rsi_divergence")
        if rsi_div and getattr(rsi_div, "detected", False) and getattr(rsi_div, "divergence_type", "none") in ("bullish", "bearish"):
            div_type = rsi_div.divergence_type
            signal = "BUY" if div_type == "bullish" else "SELL"
            strength = min(getattr(rsi_div, "strength", 0.5), 1.0)
            regime_align = 0.8 if regime == MarketRegime.RANGING else 0.6
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(max(strength, 0.45), regime_align, vol_confirm, 0.6, symbol)
            if score >= MIN_SETUP_SCORE:
                setups.append(RankedSetup(
                    symbol=symbol,
                    score=score,
                    setup_type=f"rsi_divergence_{div_type}",
                    signal=signal,
                    regime=regime.value,
                    recommended_strategy="rsi_mean_reversion",
                    reason=f"RSI {div_type} divergence detected",
                    indicators={"rsi": round(latest_rsi or 0, 2), "divergence_type": div_type},
                ))

        # ── Setup 12: Momentum breakout (price breaking 20-candle high/low) ──
        if latest_close and previous_close and closes and len(closes) >= 20:
            recent = closes[-20:]
            highest_20 = max(recent[:-1])
            lowest_20 = min(recent[:-1])
            if latest_close > highest_20 and latest_close > previous_close:
                breakout_pct = (latest_close - highest_20) / highest_20 * 100
                strength = min(breakout_pct / 2.0, 1.0)
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                trend_align = 0.9 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.4
                score = self._setup_score(max(strength, 0.35), trend_align, vol_confirm, 0.8, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="momentum_breakout_high",
                        signal="BUY",
                        regime=regime.value,
                        recommended_strategy="macd_momentum",
                        reason=f"Breaking 20-candle high (+{breakout_pct:.2f}%)",
                        indicators={"breakout_pct": round(breakout_pct, 3), "volume_ratio": round(latest_volume_ratio or 0, 2)},
                    ))
            elif latest_close < lowest_20 and latest_close < previous_close:
                breakdown_pct = (lowest_20 - latest_close) / lowest_20 * 100
                strength = min(breakdown_pct / 2.0, 1.0)
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                trend_align = 0.9 if regime == MarketRegime.TRENDING_DOWN else 0.4
                score = self._setup_score(max(strength, 0.35), trend_align, vol_confirm, 0.8, symbol)
                if score >= MIN_SETUP_SCORE:
                    setups.append(RankedSetup(
                        symbol=symbol,
                        score=score,
                        setup_type="momentum_breakout_low",
                        signal="SELL",
                        regime=regime.value,
                        recommended_strategy="rsi_mean_reversion",
                        reason=f"Breaking 20-candle low (-{breakdown_pct:.2f}%)",
                        indicators={"breakdown_pct": round(breakdown_pct, 3)},
                    ))

        return setups

    def _setup_score(
        self,
        signal_strength: float,
        regime_alignment: float,
        volume_confirmation: float,
        trend_alignment: float,
        symbol: str | None = None,
    ) -> float:
        """Compute setup ranking score with relative strength."""
        rs_score = 0.5  # default neutral
        if symbol is not None:
            rs = get_relative_strength(symbol)
            if rs is not None:
                # Map relative strength to 0-1 score
                # +5% vs BTC → 1.0, 0% → 0.5, -5% → 0.0
                rs_score = max(0.0, min(1.0, 0.5 + rs / 10.0))
        return (
            signal_strength * 0.25
            + regime_alignment * 0.20
            + volume_confirmation * 0.20
            + trend_alignment * 0.15
            + rs_score * 0.20
        )

    @staticmethod
    def _estimate_liquidity_usdt(candles: list[Any], window: int = 20) -> float:
        recent = candles[-window:]
        if not recent:
            return 0.0
        quote_volumes = [float(candle.close) * float(candle.volume) for candle in recent]
        return sum(quote_volumes) / len(quote_volumes)
