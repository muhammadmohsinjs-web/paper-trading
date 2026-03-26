"""Tests for strategy signal generation (SMA Crossover, RSI Mean Reversion, MACD Momentum, Bollinger Bounce)."""

from decimal import Decimal

from app.market.indicators import compute_indicators
from app.strategies.sma_crossover import SMACrossoverStrategy
from app.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from app.strategies.macd_momentum import MACDMomentumStrategy
from app.strategies.bollinger_bounce import BollingerBounceStrategy


USDT = Decimal("1000")


# ──────────────── SMA Crossover ────────────────


class TestSMACrossover:
    strategy = SMACrossoverStrategy()

    def test_golden_cross_buy(self):
        indicators = {
            "sma_short": [99.0, 101.0],
            "sma_long": [100.0, 100.0],
            "volume_ratio": 1.5,
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.5")

    def test_golden_cross_rejected_low_volume(self):
        indicators = {
            "sma_short": [99.0, 101.0],
            "sma_long": [100.0, 100.0],
            "volume_ratio": 0.5,  # Below 0.8 threshold
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_golden_cross_no_volume_data(self):
        indicators = {
            "sma_short": [99.0, 101.0],
            "sma_long": [100.0, 100.0],
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"

    def test_golden_cross_accepts_live_volume_ratio_shape(self):
        live_indicators = compute_indicators(
            closes=list(range(1, 80)),
            highs=[float(v + 1) for v in range(1, 80)],
            lows=[float(v - 1) for v in range(1, 80)],
            volumes=[100.0] * 79,
        )
        indicators = {
            "sma_short": [99.0, 101.0],
            "sma_long": [100.0, 100.0],
            "volume_ratio": live_indicators["volume_ratio"],
        }

        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        # Volume ratio of 1.0 (uniform volume) is >= 0.8 threshold, so signal accepted
        assert signal is not None
        assert signal.action.value == "BUY"

    def test_death_cross_sell(self):
        indicators = {
            "sma_short": [101.0, 99.0],
            "sma_long": [100.0, 100.0],
        }
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "SELL"
        assert signal.quantity_pct == Decimal("1.0")

    def test_death_cross_no_position(self):
        indicators = {
            "sma_short": [101.0, 99.0],
            "sma_long": [100.0, 100.0],
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_insufficient_data(self):
        indicators = {"sma_short": [100.0], "sma_long": [100.0]}
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_no_crossover_hold(self):
        indicators = {
            "sma_short": [101.0, 102.0],
            "sma_long": [100.0, 100.5],
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None


# ──────────────── RSI Mean Reversion ────────────────


class TestRSIMeanReversion:
    strategy = RSIMeanReversionStrategy()

    def test_buy_deep_oversold(self):
        indicators = {"rsi": [30.0, 15.0]}
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.3")  # Deep oversold without divergence

    def test_buy_moderate_oversold(self):
        indicators = {"rsi": [35.0, 22.0]}  # RSI < 25 triggers small position
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.2")

    def test_buy_blocked_has_position(self):
        indicators = {"rsi": [30.0, 15.0]}
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is None

    def test_sell_overbought(self):
        indicators = {"rsi": [65.0, 75.0]}
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "SELL"
        assert signal.quantity_pct == Decimal("1.0")

    def test_sell_no_position(self):
        indicators = {"rsi": [65.0, 75.0]}
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_hold_neutral(self):
        indicators = {"rsi": [45.0, 50.0]}
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None


# ──────────────── MACD Momentum ────────────────


class TestMACDMomentum:
    strategy = MACDMomentumStrategy()

    def test_bullish_crossover_strong(self):
        indicators = {
            "macd": (
                [-0.1, 0.5],   # macd_line: crosses above
                [0.0, 0.4],    # signal_line
                [-0.1, 0.2],   # histogram: accelerating and > 0
            ),
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.5")

    def test_bullish_crossover_standard(self):
        indicators = {
            "macd": (
                [-0.1, 0.5],   # macd_line: crosses above
                [0.0, 0.4],    # signal_line
                [0.2, 0.1],    # histogram: decelerating
            ),
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.3")

    def test_bullish_crossover_blocked_position(self):
        indicators = {
            "macd": (
                [-0.1, 0.5],
                [0.0, 0.4],
                [-0.1, 0.2],
            ),
        }
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is None

    def test_bearish_crossover_sell(self):
        indicators = {
            "macd": (
                [0.5, -0.1],   # macd_line: crosses below
                [0.4, 0.0],    # signal_line
                [0.1, -0.1],
            ),
        }
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "SELL"
        assert signal.quantity_pct == Decimal("1.0")

    def test_bearish_crossover_no_position(self):
        indicators = {
            "macd": (
                [0.5, -0.1],
                [0.4, 0.0],
                [0.1, -0.1],
            ),
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_insufficient_data(self):
        indicators = {"macd": ([0.1], [0.2], [0.3])}
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_no_crossover_hold(self):
        indicators = {
            "macd": (
                [0.3, 0.5],   # macd consistently above signal
                [0.1, 0.2],
                [0.2, 0.3],
            ),
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None


# ──────────────── Bollinger Bounce ────────────────


class TestBollingerBounce:
    strategy = BollingerBounceStrategy()

    def test_buy_lower_band_deep(self):
        # Price well below lower band (depth > 0.1 of bandwidth)
        indicators = {
            "bollinger_bands": ([110.0], [100.0], [90.0]),
            "latest_close": 87.0,  # 3 below lower, depth = 3/20 = 0.15 > 0.1
            "previous_close": 91.0,
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.5")

    def test_buy_lower_band_shallow(self):
        # Price at lower band (depth <= 0.1)
        indicators = {
            "bollinger_bands": ([110.0], [100.0], [90.0]),
            "latest_close": 90.0,  # exactly at lower, depth = 0
            "previous_close": 91.0,
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "BUY"
        assert signal.quantity_pct == Decimal("0.3")

    def test_buy_blocked_position(self):
        indicators = {
            "bollinger_bands": ([110.0], [100.0], [90.0]),
            "latest_close": 87.0,
            "previous_close": 91.0,
        }
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is None

    def test_sell_upper_band(self):
        indicators = {
            "bollinger_bands": ([110.0], [100.0], [90.0]),
            "latest_close": 110.0,
            "previous_close": 108.0,
        }
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "SELL"
        assert signal.quantity_pct == Decimal("1.0")

    def test_sell_middle_cross_down(self):
        indicators = {
            "bollinger_bands": ([110.0], [100.0], [90.0]),
            "latest_close": 99.0,   # below middle
            "previous_close": 101.0,  # was above middle
        }
        signal = self.strategy.decide(indicators, has_position=True, available_usdt=USDT)
        assert signal is not None
        assert signal.action.value == "SELL"

    def test_hold_between_bands(self):
        indicators = {
            "bollinger_bands": ([110.0], [100.0], [90.0]),
            "latest_close": 100.0,
            "previous_close": 99.0,
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None

    def test_zero_bandwidth(self):
        # upper == lower (edge case, zero std dev) — no valid band width, skip
        indicators = {
            "bollinger_bands": ([100.0], [100.0], [100.0]),
            "latest_close": 100.0,
            "previous_close": 100.0,
        }
        signal = self.strategy.decide(indicators, has_position=False, available_usdt=USDT)
        assert signal is None  # Zero bandwidth = degenerate bands, no signal
