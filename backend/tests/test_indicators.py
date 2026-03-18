"""Tests for technical indicator calculations."""

from app.market.indicators import sma, ema, rsi, macd


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
    # Constant input → EMA should converge to input
    assert abs(result[-1] - 10.0) < 0.001


def test_ema_responds_to_change():
    closes = [100.0] * 20 + [200.0] * 10
    result = ema(closes, 10)
    # Last values should be closer to 200 than 100
    assert result[-1] > 150.0


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
