"""Opportunity scanner — scans multiple symbols for trading setups."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.regime.classifier import RegimeClassifier
from app.regime.types import MarketRegime
from app.scanner.types import RankedSetup, ScanResult
from app.selector.selector import REGIME_AFFINITY

logger = logging.getLogger(__name__)

# Default symbols to scan (top by volume on Binance)
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
    "APTUSDT", "OPUSDT", "ARBUSDT", "SUIUSDT", "SEIUSDT",
]

MIN_SETUP_SCORE = 0.3
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
        overall_regime = "unknown"

        for symbol in self.symbols:
            candles = store.get_candles(symbol, interval, 200)
            if len(candles) < MIN_CANDLES_FOR_SCAN:
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
            setups = self._detect_setups(symbol, indicators, regime_result.regime)
            opportunities.extend(setups)

        # Sort by score descending
        opportunities.sort(key=lambda s: s.score, reverse=True)

        return ScanResult(
            scanned_at=datetime.now(timezone.utc).isoformat(),
            symbols_scanned=symbols_with_data,
            regime=overall_regime,
            opportunities=opportunities[:max_results],
        )

    def _detect_setups(
        self,
        symbol: str,
        indicators: dict[str, Any],
        regime: MarketRegime,
    ) -> list[RankedSetup]:
        """Detect trading setups for a single symbol."""
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

        # Setup 1: RSI Oversold
        if latest_rsi is not None and latest_rsi < 30:
            strength = max(0, (30 - latest_rsi) / 30)
            regime_align = 1.0 if regime == MarketRegime.RANGING else 0.5
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(strength, regime_align, vol_confirm, 0.5)
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

        # Setup 2: RSI Overbought
        if latest_rsi is not None and latest_rsi > 70:
            strength = max(0, (latest_rsi - 70) / 30)
            regime_align = 1.0 if regime == MarketRegime.RANGING else 0.5
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(strength, regime_align, vol_confirm, 0.5)
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

        # Setup 3: Bollinger Band squeeze (low width = potential breakout)
        if bb_upper and bb_middle and bb_lower and bb_middle[-1] != 0:
            current_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            if len(bb_upper) >= 50:
                widths = [
                    (bb_upper[i] - bb_lower[i]) / bb_middle[i]
                    for i in range(max(0, len(bb_upper) - 50), len(bb_upper))
                    if bb_middle[i] != 0
                ]
                pct_rank = sum(1 for w in widths if w > current_width) / len(widths)
                if pct_rank > 0.8:  # Current width is in lowest 20%
                    strength = pct_rank
                    vol_confirm = min(latest_volume_ratio / 1.5, 1.0) if latest_volume_ratio and latest_volume_ratio > 1.5 else 0.3
                    score = self._setup_score(strength, 0.7, vol_confirm, 0.6)
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

        # Setup 4: SMA crossover proximity
        if len(sma_short) >= 2 and len(sma_long) >= 2:
            gap_pct = abs(sma_short[-1] - sma_long[-1]) / sma_long[-1] * 100 if sma_long[-1] != 0 else 999
            if gap_pct < 0.5:  # Within 0.5% — potential crossover
                approaching_golden = sma_short[-1] > sma_short[-2] and sma_short[-1] < sma_long[-1]
                if approaching_golden:
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    trend_align = 1.0 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.3
                    score = self._setup_score(0.7, trend_align, vol_confirm, 0.6)
                    if score >= MIN_SETUP_SCORE:
                        setups.append(RankedSetup(
                            symbol=symbol,
                            score=score,
                            setup_type="sma_crossover_proximity",
                            signal="BUY",
                            regime=regime.value,
                            recommended_strategy="sma_crossover",
                            reason=f"SMA approaching golden cross (gap: {gap_pct:.2f}%)",
                            indicators={"sma_gap_pct": round(gap_pct, 3)},
                        ))

        # Setup 5: Volume breakout
        if latest_volume_ratio is not None and latest_volume_ratio > 2.0:
            if latest_close and indicators.get("previous_close"):
                price_up = latest_close > indicators["previous_close"]
                strength = min((latest_volume_ratio - 2.0) / 2.0, 1.0)
                trend_align = 1.0 if regime in (MarketRegime.TRENDING_UP,) and price_up else 0.5
                score = self._setup_score(strength, trend_align, 1.0, 0.7)
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

        return setups

    @staticmethod
    def _setup_score(
        signal_strength: float,
        regime_alignment: float,
        volume_confirmation: float,
        trend_alignment: float,
    ) -> float:
        """Compute setup ranking score."""
        return (
            signal_strength * 0.30
            + regime_alignment * 0.25
            + volume_confirmation * 0.20
            + trend_alignment * 0.15
            + 0.5 * 0.10  # liquidity placeholder
        )
