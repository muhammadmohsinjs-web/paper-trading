"""Binance WebSocket client for real-time kline streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

import websockets

from app.api.ws import ConnectionManager
from app.config import get_settings
from app.market.data_store import Candle, DataStore

logger = logging.getLogger(__name__)

ANSI_RESET = "\033[0m"
ANSI_CYAN = "\033[96m"
ANSI_GREEN = "\033[92m"
ANSI_RED = "\033[91m"
ANSI_YELLOW = "\033[93m"
ANSI_DIM = "\033[2m"
ANSI_ENABLED = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


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
        self._last_logged_price: float | None = None

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
        logger.info(
            "stream starting symbol=%s interval=%s",
            self.symbol.upper(),
            self.interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("stream stopped symbol=%s interval=%s", self.symbol.upper(), self.interval)

    def _format_live_price_log(self, symbol: str, candle: Candle, use_color: bool = ANSI_ENABLED) -> str:
        previous_price = self._last_logged_price
        self._last_logged_price = candle.close

        def colorize(value: str, ansi_code: str) -> str:
            if not use_color:
                return value
            return f"{ansi_code}{value}{ANSI_RESET}"

        delta = 0.0 if previous_price is None else candle.close - previous_price
        if previous_price is None:
            delta_label = colorize("NEW", ANSI_YELLOW)
            price_label = colorize(f"{candle.close:,.2f}", ANSI_CYAN)
        elif delta > 0:
            delta_label = colorize(f"+{delta:,.2f}", ANSI_GREEN)
            price_label = colorize(f"{candle.close:,.2f}", ANSI_GREEN)
        elif delta < 0:
            delta_label = colorize(f"{delta:,.2f}", ANSI_RED)
            price_label = colorize(f"{candle.close:,.2f}", ANSI_RED)
        else:
            delta_label = colorize("0.00", ANSI_DIM)
            price_label = colorize(f"{candle.close:,.2f}", ANSI_YELLOW)

        candle_open = datetime.fromtimestamp(candle.open_time / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        return (
            f"{colorize('[LIVE]', ANSI_CYAN)} "
            f"{symbol}/{self.interval} "
            f"price={price_label} "
            f"change={delta_label} "
            f"{colorize(f'candle_open={candle_open}', ANSI_DIM)}"
        )

    async def _run(self) -> None:
        store = DataStore.get_instance()
        manager = ConnectionManager.get_instance()
        symbol_upper = self.symbol.upper()

        while self._running:
            try:
                async with websockets.connect(self.stream_url) as ws:
                    logger.info(
                        "stream connected symbol=%s interval=%s url=%s",
                        symbol_upper,
                        self.interval,
                        self.stream_url,
                    )
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
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(self._format_live_price_log(symbol_upper, candle))
                            await manager.broadcast(
                                {
                                    "type": "price_update",
                                    "symbol": symbol_upper,
                                    "interval": self.interval,
                                    "price": candle.close,
                                    "open_time": candle.open_time,
                                }
                            )
                        except (KeyError, ValueError) as exc:
                            logger.warning("bad ws message symbol=%s error=%s", symbol_upper, exc)
            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    logger.exception(
                        "stream disconnected symbol=%s retry_in_seconds=5",
                        symbol_upper,
                    )
                    # Backfill any candles missed during disconnect
                    try:
                        from app.market.binance_rest import backfill
                        await backfill(symbol_upper, self.interval)
                        logger.info("post-reconnect backfill complete symbol=%s interval=%s", symbol_upper, self.interval)
                    except Exception:
                        logger.exception("post-reconnect backfill failed symbol=%s", symbol_upper)
                    await asyncio.sleep(5)
