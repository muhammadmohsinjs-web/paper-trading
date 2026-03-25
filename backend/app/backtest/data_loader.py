"""Historical candle data fetcher with caching for backtesting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_CANDLES_PER_REQUEST = 1000


@dataclass
class HistoricalCandle:
    """OHLCV candle for backtesting."""

    open_time: int  # ms timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int  # ms timestamp


async def fetch_historical_candles(
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
) -> list[HistoricalCandle]:
    """Fetch historical candles from Binance REST API with pagination.

    Automatically paginates through the date range using MAX_CANDLES_PER_REQUEST
    per request. Respects Binance rate limits.
    """
    all_candles: list[HistoricalCandle] = []
    current_start = start_time_ms

    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_start < end_time_ms:
            params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": current_start,
                "endTime": end_time_ms,
                "limit": MAX_CANDLES_PER_REQUEST,
            }

            try:
                response = await client.get(BINANCE_KLINES_URL, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                logger.error("Failed to fetch candles: %s", e)
                break

            if not data:
                break

            for kline in data:
                candle = HistoricalCandle(
                    open_time=int(kline[0]),
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                    volume=float(kline[5]),
                    close_time=int(kline[6]),
                )
                all_candles.append(candle)

            # Move start to after the last candle's close time
            last_close_time = int(data[-1][6])
            if last_close_time >= end_time_ms:
                break
            current_start = last_close_time + 1

            # Safety: if we got fewer than requested, we've hit the end
            if len(data) < MAX_CANDLES_PER_REQUEST:
                break

    logger.info(
        "Fetched %d historical candles for %s/%s",
        len(all_candles), symbol, interval,
    )
    return all_candles
