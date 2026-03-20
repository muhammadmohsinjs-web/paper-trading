"""Tests for technical indicator calculations."""

from app.market.indicators import atr, bollinger_bands, compute_indicators, ema, macd, rsi, sma


def test_sma_basic():
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = sma(closes, 3)
    assert len(result) == 3
    assert abs(result[0] - 20.0) < 0.001
    assert abs(result[1] - 30.0) < 0.001
    assert abs(result[2] - 40.0) < 0.001


def test_sma_insufficient_data():
    result = sma([10.0, 20.0], 5)
    assert result == []


def test_ema_basic():
    closes = [10.0] * 20
    result = ema(closes, 10)
    # Constant input → EMA should equal input; length = 20 - 10 + 1 = 11
    assert len(result) == 11
    assert abs(result[-1] - 10.0) < 0.001
    assert abs(result[0] - 10.0) < 0.001  # seed is SMA of first 10 = 10.0


def test_ema_seed_is_sma():
    closes = list(range(1, 11))  # 1..10
    result = ema(closes, 5)
    # Seed should be SMA of first 5 values = (1+2+3+4+5)/5 = 3.0
    assert abs(result[0] - 3.0) < 0.001


def test_ema_responds_to_change():
    closes = [100.0] * 20 + [200.0] * 10
    result = ema(closes, 10)
    # Length = 30 - 10 + 1 = 21
    assert len(result) == 21
    # Last values should be closer to 200 than 100
    assert result[-1] > 150.0


def test_ema_insufficient_data():
    result = ema([10.0, 20.0], 5)
    assert result == []


def test_rsi_returns_values():
    # Generate simple trending data
    closes = [float(i) for i in range(100)]
    result = rsi(closes, 14)
    assert len(result) > 0
    # Uptrend should give high RSI
    assert result[-1] > 50.0


def test_rsi_insufficient_data():
    result = rsi([10.0, 20.0], 14)
    assert result == []


def test_macd_returns_three_lists():
    closes = [float(50000 + i * 10) for i in range(100)]
    macd_line, signal_line, histogram = macd(closes)
    assert len(macd_line) > 0
    assert len(signal_line) > 0
    assert len(histogram) > 0
    assert len(macd_line) == len(signal_line) == len(histogram)


def test_atr_basic():
    n = 30
    highs = [float(100 + i * 0.5) for i in range(n)]
    lows = [float(99 + i * 0.5) for i in range(n)]
    closes = [float(99.5 + i * 0.5) for i in range(n)]
    result = atr(highs, lows, closes, period=14)
    # Should return n - 1 (TR starts at 1) - 14 + 1 = n - 14 values
    assert len(result) == n - 14
    # All ATR values should be positive
    assert all(v > 0 for v in result)


def test_atr_insufficient_data():
    result = atr([100.0] * 5, [99.0] * 5, [99.5] * 5, period=14)
    assert result == []


def test_bollinger_bands_basic():
    closes = [float(100 + i) for i in range(30)]
    upper, middle, lower = bollinger_bands(closes, period=20)
    # Length = 30 - 20 + 1 = 11
    assert len(upper) == 11
    assert len(middle) == 11
    assert len(lower) == 11
    # Upper > middle > lower
    for u, m, l in zip(upper, middle, lower):
        assert u > m > l


def test_bollinger_bands_insufficient_data():
    upper, middle, lower = bollinger_bands([100.0] * 5, period=20)
    assert upper == [] and middle == [] and lower == []


def test_compute_indicators_includes_volume_ratio():
    closes = [float(100 + i) for i in range(30)]
    highs = [close + 1 for close in closes]
    lows = [close - 1 for close in closes]
    volumes = [float(1000 + i * 10) for i in range(30)]

    result = compute_indicators(closes, {"volume_ma_period": 20}, highs=highs, lows=lows, volumes=volumes)

    assert "volume_sma" in result
    assert "volume_ratio" in result
    assert len(result["volume_sma"]) == 11
    assert len(result["volume_ratio"]) == 11
    assert result["latest_close"] == closes[-1]
    assert result["previous_close"] == closes[-2]


def test_sma_period_1():
    closes = [10.0, 20.0, 30.0]
    result = sma(closes, 1)
    assert result == closes


def test_sma_period_equals_data_length():
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = sma(closes, 5)
    assert len(result) == 1
    assert abs(result[0] - 30.0) < 0.001


def test_rsi_all_gains():
    closes = [float(100 + i) for i in range(30)]
    result = rsi(closes, 14)
    assert len(result) > 0
    assert result[-1] > 95.0


def test_rsi_all_losses():
    closes = [float(100 - i) for i in range(30)]
    result = rsi(closes, 14)
    assert len(result) > 0
    assert result[-1] < 5.0


def test_rsi_equal_gains_losses():
    closes = []
    for i in range(30):
        closes.append(100.0 + (1 if i % 2 == 0 else -1))
    result = rsi(closes, 14)
    assert len(result) > 0
    assert abs(result[-1] - 50.0) < 10.0


def test_macd_constant_input():
    closes = [100.0] * 50
    macd_line, signal_line, histogram = macd(closes)
    if macd_line:
        assert abs(macd_line[-1]) < 0.001
    if histogram:
        assert abs(histogram[-1]) < 0.001


def test_atr_constant_range():
    n = 30
    highs = [101.0] * n
    lows = [99.0] * n
    closes = [100.0] * n
    result = atr(highs, lows, closes, period=14)
    assert len(result) > 0
    for v in result:
        assert abs(v - result[0]) < 0.1


def test_bollinger_constant_input():
    closes = [100.0] * 25
    upper, middle, lower = bollinger_bands(closes, period=20)
    assert len(upper) > 0
    assert abs(upper[-1] - middle[-1]) < 0.001
    assert abs(lower[-1] - middle[-1]) < 0.001


def test_compute_indicators_no_optional_data():
    closes = [float(100 + i) for i in range(60)]
    result = compute_indicators(closes)
    assert "atr" not in result
    assert "volume_sma" not in result
    assert "volume_ratio" not in result
