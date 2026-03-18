"""Market data endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.market.data_store import DataStore

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price/{symbol}")
async def get_price(symbol: str):
    store = DataStore.get_instance()
    price = store.get_latest_price(symbol.upper())
    if price is None:
        raise HTTPException(404, f"No price data for {symbol}")
    return {"symbol": symbol.upper(), "price": price}


@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    interval: str = Query("5m"),
    limit: int = Query(100, ge=1, le=500),
):
    store = DataStore.get_instance()
    candles = store.get_candles(symbol.upper(), interval, limit)
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "count": len(candles),
        "candles": [
            {
                "open_time": c.open_time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ],
    }
