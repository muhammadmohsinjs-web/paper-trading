"""Relative strength ranking — compare coin performance vs BTC.

In crypto, coins that outperform BTC tend to continue outperforming
(momentum effect). Coins underperforming BTC are often in distribution
and should be avoided for long entries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.market.data_store import DataStore

logger = logging.getLogger(__name__)

BTC_SYMBOL = "BTCUSDT"


@dataclass(frozen=True)
class RelativeStrengthResult:
    symbol: str
    pct_change: float  # Symbol's % change over lookback
    btc_pct_change: float  # BTC's % change over lookback
    relative_strength: float  # symbol_change - btc_change
    rank: int


def _pct_change(candles: list, lookback: int) -> float | None:
    """Calculate % change over the last N candles."""
    if len(candles) < lookback:
        return None
    old_close = candles[-lookback].close
    new_close = candles[-1].close
    if old_close == 0:
        return None
    return (new_close - old_close) / old_close * 100


def rank_by_relative_strength(
    symbols: list[str],
    interval: str = "1h",
    lookback_candles: int = 24,
) -> list[RelativeStrengthResult]:
    """Rank symbols by their performance relative to BTC.

    Args:
        symbols: List of symbols to rank.
        interval: Candle interval to use.
        lookback_candles: Number of candles to measure change over.
            Default 24 on 1h = 24 hours of relative performance.

    Returns:
        List of RelativeStrengthResult sorted by relative_strength descending.
    """
    store = DataStore.get_instance()

    # Get BTC baseline
    btc_candles = store.get_candles(BTC_SYMBOL, interval, lookback_candles + 1)
    btc_change = _pct_change(btc_candles, lookback_candles)
    if btc_change is None:
        logger.debug("Cannot compute BTC relative strength: insufficient data")
        return []

    results: list[RelativeStrengthResult] = []
    for symbol in symbols:
        if symbol == BTC_SYMBOL:
            continue
        candles = store.get_candles(symbol, interval, lookback_candles + 1)
        change = _pct_change(candles, lookback_candles)
        if change is None:
            continue
        results.append(RelativeStrengthResult(
            symbol=symbol,
            pct_change=round(change, 4),
            btc_pct_change=round(btc_change, 4),
            relative_strength=round(change - btc_change, 4),
            rank=0,  # Will be set after sorting
        ))

    # Sort by relative strength descending
    results.sort(key=lambda r: r.relative_strength, reverse=True)

    # Assign ranks
    ranked = [
        RelativeStrengthResult(
            symbol=r.symbol,
            pct_change=r.pct_change,
            btc_pct_change=r.btc_pct_change,
            relative_strength=r.relative_strength,
            rank=idx + 1,
        )
        for idx, r in enumerate(results)
    ]
    return ranked


def get_relative_strength(
    symbol: str,
    interval: str = "1h",
    lookback_candles: int = 24,
) -> float | None:
    """Get relative strength for a single symbol vs BTC.

    Returns positive value if outperforming BTC, negative if underperforming.
    Returns None if data is insufficient.
    """
    store = DataStore.get_instance()
    btc_candles = store.get_candles(BTC_SYMBOL, interval, lookback_candles + 1)
    btc_change = _pct_change(btc_candles, lookback_candles)
    if btc_change is None:
        return None

    if symbol == BTC_SYMBOL:
        return 0.0

    candles = store.get_candles(symbol, interval, lookback_candles + 1)
    change = _pct_change(candles, lookback_candles)
    if change is None:
        return None

    return round(change - btc_change, 4)
