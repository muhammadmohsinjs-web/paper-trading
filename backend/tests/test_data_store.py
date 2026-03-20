"""Tests for the in-memory market data store (ring buffer, singleton, thread safety)."""

import threading
from app.market.data_store import Candle, DataStore


def _candle(open_time: int, close: float = 85000.0) -> Candle:
    return Candle(
        open_time=open_time,
        open=close - 10,
        high=close + 50,
        low=close - 50,
        close=close,
        volume=1000.0,
    )


class TestDataStore:
    def setup_method(self):
        DataStore.reset()
        self.store = DataStore(max_candles=500)

    def teardown_method(self):
        DataStore.reset()

    def test_ring_buffer_cap_500(self):
        candles = [_candle(i) for i in range(600)]
        self.store.set_candles("BTC", "5m", candles)
        result = self.store.get_candles("BTC", "5m", limit=600)
        assert len(result) == 500

    def test_set_candles_backfill_200(self):
        candles = [_candle(i) for i in range(200)]
        self.store.set_candles("BTC", "5m", candles)
        result = self.store.get_candles("BTC", "5m", limit=200)
        assert len(result) == 200

    def test_set_candles_trims_to_max(self):
        candles = [_candle(i) for i in range(700)]
        self.store.set_candles("BTC", "5m", candles)
        result = self.store.get_candles("BTC", "5m", limit=1000)
        assert len(result) == 500

    def test_update_candle_appends_new(self):
        self.store.set_candles("BTC", "5m", [_candle(1), _candle(2)])
        self.store.update_candle("BTC", "5m", _candle(3))
        result = self.store.get_candles("BTC", "5m")
        assert len(result) == 3

    def test_update_candle_replaces_same_timestamp(self):
        self.store.set_candles("BTC", "5m", [_candle(1), _candle(2, close=100.0)])
        self.store.update_candle("BTC", "5m", _candle(2, close=200.0))
        result = self.store.get_candles("BTC", "5m")
        assert len(result) == 2
        assert result[-1].close == 200.0

    def test_get_closes_returns_floats(self):
        candles = [_candle(i, close=float(100 + i)) for i in range(50)]
        self.store.set_candles("BTC", "5m", candles)
        closes = self.store.get_closes("BTC", "5m", limit=50)
        assert len(closes) == 50
        assert all(isinstance(c, float) for c in closes)

    def test_get_candles_limit(self):
        candles = [_candle(i) for i in range(200)]
        self.store.set_candles("BTC", "5m", candles)
        result = self.store.get_candles("BTC", "5m", limit=100)
        assert len(result) == 100
        # Should return the last 100
        assert result[0].open_time == 100

    def test_get_latest_price(self):
        candles = [_candle(i, close=float(100 + i)) for i in range(10)]
        self.store.set_candles("BTC", "5m", candles)
        assert self.store.get_latest_price("BTC") == 109.0

    def test_thread_safety_concurrent_rw(self):
        candles = [_candle(i) for i in range(100)]
        self.store.set_candles("BTC", "5m", candles)
        errors = []

        def writer():
            try:
                for i in range(100, 200):
                    self.store.update_candle("BTC", "5m", _candle(i))
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    self.store.get_candles("BTC", "5m")
                    self.store.get_closes("BTC", "5m")
                    self.store.get_latest_price("BTC")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_singleton_get_instance(self):
        DataStore.reset()
        a = DataStore.get_instance()
        b = DataStore.get_instance()
        assert a is b

    def test_reset_clears_singleton(self):
        a = DataStore.get_instance()
        DataStore.reset()
        b = DataStore.get_instance()
        assert a is not b

    def test_data_slicing_last_n(self):
        candles = [_candle(i, close=float(i)) for i in range(200)]
        self.store.set_candles("BTC", "5m", candles)
        result = self.store.get_candles("BTC", "5m", limit=50)
        assert len(result) == 50
        assert result[0].close == 150.0  # 200 - 50 = 150

    def test_empty_store(self):
        result = self.store.get_candles("BTC", "5m")
        assert result == []
        assert self.store.get_latest_price("BTC") is None
        assert self.store.get_closes("BTC", "5m") == []
