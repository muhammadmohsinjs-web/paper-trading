"""Binance REST client for historical candle backfill."""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.market.data_store import Candle, DataStore

logger = logging.getLogger(__name__)


async def fetch_candles(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    limit: int = 200,
) -> list[Candle]:
    """Fetch historical klines from Binance REST API (no API key needed)."""
    settings = get_settings()
    url = f"{settings.binance_rest_url}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    candles: list[Candle] = []
    for k in data:
        candles.append(
            Candle(
                open_time=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
            )
        )
    return candles


async def backfill(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    limit: int = 200,
) -> None:
    """Backfill the DataStore with historical candles on startup."""
    store = DataStore.get_instance()
    try:
        candles = await fetch_candles(symbol, interval, limit)
        store.set_candles(symbol, interval, candles)
        logger.info("Backfilled %d candles for %s/%s", len(candles), symbol, interval)
    except Exception:
        logger.exception("Failed to backfill candles for %s/%s", symbol, interval)
