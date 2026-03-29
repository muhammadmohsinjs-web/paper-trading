"""Binance REST client for historical candle backfill."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import logging

import httpx

from app.config import get_settings
from app.market.data_store import Candle, DataStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    bid_price: float
    ask_price: float
    mid_price: float
    spread_bps: float
    bid_depth_usdt: float
    ask_depth_usdt: float
    depth_band_bps: float
    depth_levels: int

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def _sum_depth_notional(
    levels: list[list[str]],
    *,
    mid_price: float,
    side: str,
    depth_band_bps: float,
) -> float:
    if mid_price <= 0:
        return 0.0

    total = 0.0
    for level in levels:
        if len(level) < 2:
            continue
        price = float(level[0])
        quantity = float(level[1])
        if price <= 0 or quantity <= 0:
            continue

        distance_bps = abs(price - mid_price) / mid_price * 10_000.0
        if distance_bps > depth_band_bps:
            if side == "ask" and price > mid_price:
                break
            if side == "bid" and price < mid_price:
                break
            continue
        total += price * quantity
    return total


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


async def fetch_order_book_snapshot(
    symbol: str,
    *,
    depth_limit: int = 20,
    depth_band_bps: float = 35.0,
) -> OrderBookSnapshot:
    """Fetch best bid/ask and shallow order-book depth for a symbol."""
    settings = get_settings()
    book_ticker_url = f"{settings.binance_rest_url}/api/v3/ticker/bookTicker"
    depth_url = f"{settings.binance_rest_url}/api/v3/depth"

    async with httpx.AsyncClient(timeout=10.0) as client:
        book_resp, depth_resp = await asyncio.gather(
            client.get(book_ticker_url, params={"symbol": symbol}),
            client.get(depth_url, params={"symbol": symbol, "limit": depth_limit}),
        )
        book_resp.raise_for_status()
        depth_resp.raise_for_status()
        book_payload = book_resp.json()
        depth_payload = depth_resp.json()

    bid_price = float(book_payload["bidPrice"])
    ask_price = float(book_payload["askPrice"])
    mid_price = (bid_price + ask_price) / 2.0 if bid_price > 0 and ask_price > 0 else 0.0
    spread_bps = ((ask_price - bid_price) / mid_price * 10_000.0) if mid_price > 0 else 0.0

    bids = depth_payload.get("bids", [])
    asks = depth_payload.get("asks", [])
    bid_depth_usdt = _sum_depth_notional(
        bids,
        mid_price=mid_price,
        side="bid",
        depth_band_bps=depth_band_bps,
    )
    ask_depth_usdt = _sum_depth_notional(
        asks,
        mid_price=mid_price,
        side="ask",
        depth_band_bps=depth_band_bps,
    )

    return OrderBookSnapshot(
        symbol=symbol,
        bid_price=round(bid_price, 8),
        ask_price=round(ask_price, 8),
        mid_price=round(mid_price, 8),
        spread_bps=round(spread_bps, 4),
        bid_depth_usdt=round(bid_depth_usdt, 2),
        ask_depth_usdt=round(ask_depth_usdt, 2),
        depth_band_bps=round(depth_band_bps, 2),
        depth_levels=depth_limit,
    )


async def backfill(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    limit: int = 200,
) -> int:
    """Backfill the DataStore with historical candles on startup."""
    store = DataStore.get_instance()
    try:
        candles = await fetch_candles(symbol, interval, limit)
        store.set_candles(symbol, interval, candles)
        logger.info(
            "backfill complete symbol=%s interval=%s candles=%d",
            symbol,
            interval,
            len(candles),
        )
        return len(candles)
    except Exception:
        logger.exception("backfill failed symbol=%s interval=%s", symbol, interval)
        return 0
