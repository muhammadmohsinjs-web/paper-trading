"""In-memory market data store using deque ring buffers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from threading import Lock


@dataclass
class Candle:
    open_time: int  # epoch ms
    open: float
    high: float
    low: float
    close: float
    volume: float


class DataStore:
    """Singleton-style in-memory store for candle data and latest prices.

    Thread-safe for reads. Writes happen from a single async task (WS listener).
    """

    _instance: DataStore | None = None

    def __init__(self, max_candles: int = 500) -> None:
        self._max = max_candles
        # key: (symbol, interval) → deque of Candles
        self._candles: dict[tuple[str, str], deque[Candle]] = {}
        self._latest_prices: dict[str, float] = {}
        self._lock = Lock()

    @classmethod
    def get_instance(cls) -> DataStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def update_candle(self, symbol: str, interval: str, candle: Candle) -> None:
        key = (symbol, interval)
        with self._lock:
            if key not in self._candles:
                self._candles[key] = deque(maxlen=self._max)
            buf = self._candles[key]
            # Update last candle if same open_time, else append
            if buf and buf[-1].open_time == candle.open_time:
                buf[-1] = candle
            else:
                buf.append(candle)
            self._latest_prices[symbol] = candle.close

    def set_candles(self, symbol: str, interval: str, candles: list[Candle]) -> None:
        key = (symbol, interval)
        with self._lock:
            buf = deque(candles[-self._max :], maxlen=self._max)
            self._candles[key] = buf
            if candles:
                self._latest_prices[symbol] = candles[-1].close

    def get_candles(
        self, symbol: str, interval: str, limit: int = 200
    ) -> list[Candle]:
        key = (symbol, interval)
        with self._lock:
            buf = self._candles.get(key, deque())
            items = list(buf)
        return items[-limit:]

    def get_latest_price(self, symbol: str) -> float | None:
        return self._latest_prices.get(symbol)

    def get_closes(self, symbol: str, interval: str, limit: int = 200) -> list[float]:
        candles = self.get_candles(symbol, interval, limit)
        return [c.close for c in candles]
