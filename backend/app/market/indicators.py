"""Technical indicator calculations using numpy."""

from __future__ import annotations

import numpy as np

from app.market.divergence import detect_rsi_divergence
from app.market.structure import find_sr_levels


def sma(closes: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    if len(closes) < period:
        return []
    arr = np.array(closes, dtype=np.float64)
    kernel = np.ones(period) / period
    result = np.convolve(arr, kernel, mode="valid")
    return result.tolist()


def ema(closes: list[float], period: int) -> list[float]:
    """Exponential Moving Average.

    Initialises with the SMA of the first *period* values (standard method)
    and returns ``len(closes) - period + 1`` values — the same length
    convention used by :func:`sma`.
    """
    if len(closes) < period:
        return []
    arr = np.array(closes, dtype=np.float64)
    multiplier = 2.0 / (period + 1)
    seed = float(np.mean(arr[:period]))
    result = [seed]
    for i in range(period, len(arr)):
        result.append((arr[i] - result[-1]) * multiplier + result[-1])
    return result


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


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Average True Range (Wilder's smoothing).

    Returns ``len(closes) - period`` values.
    """
    n = len(closes)
    if n < period + 1 or len(highs) < n or len(lows) < n:
        return []

    h = np.array(highs, dtype=np.float64)
    l = np.array(lows, dtype=np.float64)
    c = np.array(closes, dtype=np.float64)

    # True Range starts at index 1 (needs previous close)
    tr = np.maximum(
        h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])),
    )

    # Wilder's smoothing (same approach as RSI)
    avg = float(np.mean(tr[:period]))
    result = [avg]
    for i in range(period, len(tr)):
        avg = (avg * (period - 1) + float(tr[i])) / period
        result.append(avg)
    return result


def bollinger_bands(
    closes: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    """Bollinger Bands: returns (upper, middle, lower).

    Each list has ``len(closes) - period + 1`` values.
    """
    if len(closes) < period:
        return [], [], []

    arr = np.array(closes, dtype=np.float64)
    middle: list[float] = []
    upper: list[float] = []
    lower: list[float] = []

    for i in range(period - 1, len(arr)):
        window = arr[i - period + 1 : i + 1]
        mean = float(np.mean(window))
        std = float(np.std(window, ddof=0))
        middle.append(mean)
        upper.append(mean + std_dev * std)
        lower.append(mean - std_dev * std)

    return upper, middle, lower


def adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Average Directional Index — measures trend strength (0-100).

    ADX > 25 indicates a strong trend; ADX < 20 indicates ranging/consolidation.
    Returns ``len(closes) - 2*period`` values (needs extra period for smoothing).
    """
    n = len(closes)
    if n < 2 * period + 1 or len(highs) < n or len(lows) < n:
        return []

    h = np.array(highs, dtype=np.float64)
    l = np.array(lows, dtype=np.float64)
    c = np.array(closes, dtype=np.float64)

    # True Range
    tr = np.maximum(
        h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])),
    )

    # +DM and -DM
    up_move = h[1:] - h[:-1]
    down_move = l[:-1] - l[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Wilder's smoothing for TR, +DM, -DM
    def wilder_smooth(values: np.ndarray, p: int) -> list[float]:
        avg = float(np.sum(values[:p]))
        result = [avg]
        for i in range(p, len(values)):
            avg = avg - avg / p + float(values[i])
            result.append(avg)
        return result

    smoothed_tr = wilder_smooth(tr, period)
    smoothed_plus_dm = wilder_smooth(plus_dm, period)
    smoothed_minus_dm = wilder_smooth(minus_dm, period)

    # +DI and -DI
    plus_di: list[float] = []
    minus_di: list[float] = []
    dx_values: list[float] = []

    for i in range(len(smoothed_tr)):
        str_val = smoothed_tr[i]
        if str_val == 0:
            plus_di.append(0.0)
            minus_di.append(0.0)
            dx_values.append(0.0)
            continue
        pdi = 100.0 * smoothed_plus_dm[i] / str_val
        mdi = 100.0 * smoothed_minus_dm[i] / str_val
        plus_di.append(pdi)
        minus_di.append(mdi)
        di_sum = pdi + mdi
        if di_sum == 0:
            dx_values.append(0.0)
        else:
            dx_values.append(100.0 * abs(pdi - mdi) / di_sum)

    # Smooth DX to get ADX
    if len(dx_values) < period:
        return []

    adx_val = float(np.mean(dx_values[:period]))
    adx_result = [adx_val]
    for i in range(period, len(dx_values)):
        adx_val = (adx_val * (period - 1) + dx_values[i]) / period
        adx_result.append(adx_val)

    return adx_result


def obv(closes: list[float], volumes: list[float]) -> list[float]:
    """On-Balance Volume — cumulative volume flow indicator."""
    if len(closes) < 2 or len(volumes) < len(closes):
        return []

    result = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            result.append(result[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            result.append(result[-1] - volumes[i])
        else:
            result.append(result[-1])
    return result


def compute_indicators(
    closes: list[float],
    config: dict | None = None,
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> dict:
    """Compute all indicators and return as a dict."""
    cfg = config or {}
    sma_short = cfg.get("sma_short", 20)
    sma_long = cfg.get("sma_long", 50)
    rsi_period = cfg.get("rsi_period", 14)
    volume_ma_period = cfg.get("volume_ma_period", 20)

    result = {
        "sma_short": sma(closes, sma_short),
        "sma_long": sma(closes, sma_long),
        "ema_12": ema(closes, 12),
        "ema_26": ema(closes, 26),
        "rsi": rsi(closes, rsi_period),
        "macd": macd(closes),
        "bollinger_bands": bollinger_bands(closes),
        "latest_close": closes[-1] if closes else None,
        "previous_close": closes[-2] if len(closes) > 1 else None,
    }

    # RSI divergence detection
    if result["rsi"]:
        result["rsi_divergence"] = detect_rsi_divergence(closes, result["rsi"])
    else:
        result["rsi_divergence"] = None

    if highs is not None and lows is not None:
        result["atr"] = atr(highs, lows, closes)
        result["adx"] = adx(highs, lows, closes)
        result["sr_levels"] = find_sr_levels(highs, lows, closes)

    if volumes is not None:
        volume_sma = sma(volumes, volume_ma_period)
        volume_ratio: list[float] = []
        for idx, avg_volume in enumerate(volume_sma):
            volume_idx = idx + volume_ma_period - 1
            current_volume = volumes[volume_idx]
            volume_ratio.append(current_volume / avg_volume if avg_volume else 0.0)

        result["volume_sma"] = volume_sma
        result["volume_ratio"] = volume_ratio
        result["latest_volume"] = volumes[-1] if volumes else None

    return result
