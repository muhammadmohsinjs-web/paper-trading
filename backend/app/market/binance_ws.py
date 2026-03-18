"""Binance WebSocket client for real-time kline streaming."""

from __future__ import annotations

import asyncio
import json
import logging

import websockets

from app.config import get_settings
from app.market.data_store import Candle, DataStore

logger = logging.getLogger(__name__)


class BinanceWSClient:
    """Async WebSocket client subscribing to Binance kline streams.

    Auto-reconnects on disconnect.
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
    ) -> None:
        self.symbol = symbol.lower()
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def stream_url(self) -> str:
        settings = get_settings()
        stream = f"{self.symbol}@kline_{self.interval}"
        return f"{settings.binance_ws_url}/{stream}"

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Binance WS started for %s/%s", self.symbol, self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Binance WS stopped")

    async def _run(self) -> None:
        store = DataStore.get_instance()
        symbol_upper = self.symbol.upper()

        while self._running:
            try:
                async with websockets.connect(self.stream_url) as ws:
                    logger.info("Connected to Binance WS: %s", self.stream_url)
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            k = msg.get("k", {})
                            candle = Candle(
                                open_time=int(k["t"]),
                                open=float(k["o"]),
                                high=float(k["h"]),
                                low=float(k["l"]),
                                close=float(k["c"]),
                                volume=float(k["v"]),
                            )
                            store.update_candle(symbol_upper, self.interval, candle)
                        except (KeyError, ValueError) as exc:
                            logger.warning("Bad WS message: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    logger.exception("WS disconnected, reconnecting in 5s...")
                    await asyncio.sleep(5)
