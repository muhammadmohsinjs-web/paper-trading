"""Technical indicator calculations using numpy."""

from __future__ import annotations

import numpy as np


def sma(closes: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    if len(closes) < period:
        return []
    arr = np.array(closes, dtype=np.float64)
    kernel = np.ones(period) / period
    result = np.convolve(arr, kernel, mode="valid")
    return result.tolist()


def ema(closes: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(closes) < period:
        return []
    arr = np.array(closes, dtype=np.float64)
    multiplier = 2.0 / (period + 1)
    result = np.empty(len(arr))
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = (arr[i] - result[i - 1]) * multiplier + result[i - 1]
    return result.tolist()


def rsi(closes: list[float], period: int = 14) -> list[float]:
    """Relative Strength Index (Wilder's smoothing)."""
    if len(closes) < period + 1:
        return []
    arr = np.array(closes, dtype=np.float64)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    rsi_values: list[float] = []
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100.0 - 100.0 / (1.0 + rs))

    return rsi_values


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    """MACD: returns (macd_line, signal_line, histogram).

    All lists are aligned to the same length.
    """
    if len(closes) < slow:
        return [], [], []

    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)

    # Align lengths
    offset = len(fast_ema) - len(slow_ema)
    fast_aligned = fast_ema[offset:]
    macd_line = [f - s for f, s in zip(fast_aligned, slow_ema)]

    signal_line = ema(macd_line, signal_period) if len(macd_line) >= signal_period else []

    # Align macd_line to signal_line length
    if signal_line:
        offset2 = len(macd_line) - len(signal_line)
        macd_trimmed = macd_line[offset2:]
        histogram = [m - s for m, s in zip(macd_trimmed, signal_line)]
        return macd_trimmed, signal_line, histogram

    return macd_line, [], []


def compute_indicators(
    closes: list[float],
    config: dict | None = None,
) -> dict:
    """Compute all indicators and return as a dict."""
    cfg = config or {}
    sma_short = cfg.get("sma_short", 10)
    sma_long = cfg.get("sma_long", 50)
    rsi_period = cfg.get("rsi_period", 14)

    return {
        "sma_short": sma(closes, sma_short),
        "sma_long": sma(closes, sma_long),
        "ema_12": ema(closes, 12),
        "ema_26": ema(closes, 26),
        "rsi": rsi(closes, rsi_period),
        "macd": macd(closes),
        "latest_close": closes[-1] if closes else None,
    }
