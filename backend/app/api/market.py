"""Market data endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.engine.composite_scorer import compute_composite_score

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


@router.get("/signal/{symbol}")
async def get_signal(
    symbol: str,
    interval: str = Query("1h"),
):
    """Return the current composite signal and per-indicator votes."""
    store = DataStore.get_instance()
    candles = store.get_candles(symbol.upper(), interval, 200)
    if len(candles) < 50:
        raise HTTPException(400, f"Not enough candle data ({len(candles)}/50)")

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    indicators = compute_indicators(closes, highs=highs, lows=lows, volumes=volumes)
    result = compute_composite_score(indicators)

    # Individual indicator snapshots for the UI
    latest_rsi = indicators["rsi"][-1] if indicators.get("rsi") else None
    latest_atr = indicators["atr"][-1] if indicators.get("atr") else None
    volume_ratio_list = indicators.get("volume_ratio", [])
    latest_volume_ratio = volume_ratio_list[-1] if volume_ratio_list else None

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "candles_used": len(candles),
        "composite_score": round(result.composite_score, 4),
        "confidence": round(result.confidence, 4),
        "direction": result.direction,
        "signal": result.signal,
        "dampening_multiplier": result.dampening_multiplier,
        "votes": {k: round(v, 4) for k, v in result.votes.items()},
        "weights": {k: round(v, 4) for k, v in result.weights.items()},
        "indicators": {
            "rsi": round(latest_rsi, 2) if latest_rsi is not None else None,
            "atr": round(latest_atr, 2) if latest_atr is not None else None,
            "volume_ratio": round(latest_volume_ratio, 3) if latest_volume_ratio is not None else None,
            "price": closes[-1],
        },
        "thresholds": {
            "buy_gate": 0.5,
            "sell_gate": -0.5,
            "confidence_gate": 0.5,
            "full_conviction": 0.8,
            "reduced_conviction": 0.6,
        },
    }
