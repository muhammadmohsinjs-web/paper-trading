"""Tests for the dynamic universe selector."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.market.data_store import Candle, DataStore
from app.scanner.types import ActivityScore, CandidateInfo
from app.scanner.universe_selector import UniverseSelector


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons before each test."""
    DataStore.reset()
    UniverseSelector.reset()
    yield
    DataStore.reset()
    UniverseSelector.reset()


def _make_candles(count: int, base_price: float = 100.0, volume: float = 1000.0) -> list[Candle]:
    """Generate synthetic candles for testing."""
    candles = []
    for i in range(count):
        price = base_price + (i * 0.1)
        candles.append(Candle(
            open_time=1700000000000 + i * 3_600_000,
            open=price - 0.5,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=volume,
        ))
    return candles


class TestScoringFunctions:
    """Test individual scoring components."""

    def test_liquidity_depth_tiers(self):
        assert UniverseSelector._score_liquidity_depth(100_000_000) == 1.0
        assert UniverseSelector._score_liquidity_depth(50_000_000) == 1.0
        assert UniverseSelector._score_liquidity_depth(20_000_000) == 0.8
        assert UniverseSelector._score_liquidity_depth(5_000_000) == 0.6
        assert UniverseSelector._score_liquidity_depth(1_000_000) == 0.3
        assert UniverseSelector._score_liquidity_depth(100_000) == 0.1

    def test_volume_surge_neutral_without_data(self):
        store = DataStore.get_instance()
        score = UniverseSelector._score_volume_surge("TESTUSDT", 1_000_000, store)
        assert score == pytest.approx(0.4)

    def test_volume_surge_with_history(self):
        store = DataStore.get_instance()
        # Load 168 candles (7 days) with consistent volume of 1000
        candles = _make_candles(168, base_price=100.0, volume=1000.0)
        store.set_candles("TESTUSDT", "1h", candles)

        # Current hourly rate: 2_400_000 / 24 = 100_000 USDT
        # Avg hourly vol from candles: ~100 * 1000 = 100_000 USDT
        # Ratio ≈ 1.0 → moderate score
        score = UniverseSelector._score_volume_surge("TESTUSDT", 2_400_000, store)
        assert 0.2 < score < 0.6

    def test_volume_surge_high_ratio(self):
        store = DataStore.get_instance()
        candles = _make_candles(168, base_price=100.0, volume=100.0)
        store.set_candles("TESTUSDT", "1h", candles)

        # Current hourly rate much higher than average → high score
        score = UniverseSelector._score_volume_surge("TESTUSDT", 10_000_000, store)
        assert score > 0.5

    def test_volatility_quality_moderate(self):
        store = DataStore.get_instance()
        # Create candles with moderate volatility (high-low spread ~2%)
        candles = []
        for i in range(20):
            price = 100.0 + i * 0.1
            candles.append(Candle(
                open_time=1700000000000 + i * 3_600_000,
                open=price,
                high=price + 1.0,  # 1% above
                low=price - 1.0,   # 1% below
                close=price,
                volume=1000.0,
            ))
        store.set_candles("TESTUSDT", "1h", candles)
        score = UniverseSelector._score_volatility_quality("TESTUSDT", 100.0, store)
        assert 0.4 < score < 1.0

    def test_volatility_quality_too_flat(self):
        store = DataStore.get_instance()
        candles = []
        for i in range(20):
            price = 100.0
            candles.append(Candle(
                open_time=1700000000000 + i * 3_600_000,
                open=price,
                high=price + 0.01,
                low=price - 0.01,
                close=price,
                volume=1000.0,
            ))
        store.set_candles("TESTUSDT", "1h", candles)
        score = UniverseSelector._score_volatility_quality("TESTUSDT", 100.0, store)
        assert score < 0.3

    def test_trend_clarity_neutral_without_data(self):
        store = DataStore.get_instance()
        score = UniverseSelector._score_trend_clarity("TESTUSDT", store)
        assert score == pytest.approx(0.3)

    def test_trend_clarity_with_trending_data(self):
        store = DataStore.get_instance()
        # Strong uptrend: price rising consistently
        candles = []
        for i in range(30):
            price = 100.0 + i * 2.0
            candles.append(Candle(
                open_time=1700000000000 + i * 3_600_000,
                open=price - 1.0,
                high=price + 1.5,
                low=price - 0.5,
                close=price,
                volume=1000.0,
            ))
        store.set_candles("TESTUSDT", "1h", candles)
        score = UniverseSelector._score_trend_clarity("TESTUSDT", store)
        assert score > 0.4  # Should show trend

    def test_relative_strength_no_data(self):
        score = UniverseSelector._score_relative_strength("TESTUSDT")
        assert score == pytest.approx(0.5)


class TestUniverseSelector:
    """Test the selector's public interface and caching."""

    def test_singleton_pattern(self):
        s1 = UniverseSelector.get_instance()
        s2 = UniverseSelector.get_instance()
        assert s1 is s2

    def test_reset(self):
        s1 = UniverseSelector.get_instance()
        UniverseSelector.reset()
        s2 = UniverseSelector.get_instance()
        assert s1 is not s2

    def test_retained_symbols_set(self):
        selector = UniverseSelector.get_instance()
        selector.set_retained_symbols({"BTCUSDT", "ETHUSDT"})
        assert selector._retained_symbols == {"BTCUSDT", "ETHUSDT"}

    def test_snapshot_initially_none(self):
        selector = UniverseSelector.get_instance()
        assert selector.get_last_snapshot() is None

    @pytest.mark.asyncio
    async def test_get_active_universe_falls_back_to_static_when_refresh_yields_no_symbols(self, monkeypatch):
        selector = UniverseSelector.get_instance()

        async def fake_refresh_candidate_pool() -> None:
            selector._candidate_pool = []

        async def fake_refresh_active_universe() -> None:
            selector._active_universe = []
            selector._active_symbols = []

        monkeypatch.setattr(selector, "_refresh_candidate_pool", fake_refresh_candidate_pool)
        monkeypatch.setattr(selector, "_refresh_active_universe", fake_refresh_active_universe)

        universe = await selector.get_active_universe(force_refresh=True)

        assert universe == get_settings().default_scan_universe


class TestActivityScore:
    """Test the ActivityScore dataclass."""

    def test_creation(self):
        score = ActivityScore(
            symbol="BTCUSDT",
            activity_score=0.85,
            volume_surge=0.9,
            volatility_quality=0.8,
            trend_clarity=0.7,
            liquidity_depth=1.0,
            relative_strength=0.6,
            volume_24h_usdt=50_000_000,
        )
        assert score.symbol == "BTCUSDT"
        assert score.activity_score == 0.85
        assert score.is_new_entrant is False

    def test_new_entrant_flag(self):
        score = ActivityScore(
            symbol="NEWUSDT",
            activity_score=0.5,
            volume_surge=0.5,
            volatility_quality=0.5,
            trend_clarity=0.5,
            liquidity_depth=0.5,
            relative_strength=0.5,
            volume_24h_usdt=1_000_000,
            is_new_entrant=True,
        )
        assert score.is_new_entrant is True


class TestCandidateInfo:
    """Test the CandidateInfo dataclass."""

    def test_creation(self):
        info = CandidateInfo(
            symbol="ETHUSDT",
            price=3500.0,
            volume_24h_usdt=100_000_000,
            price_change_pct_24h=2.5,
        )
        assert info.symbol == "ETHUSDT"
        assert info.volume_24h_usdt == 100_000_000
