"""Market data endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.market.data_store import Candle, DataStore
from app.market.indicators import compute_indicators
from app.engine.composite_scorer import compute_composite_score
from app.regime.classifier import RegimeClassifier

router = APIRouter(prefix="/market", tags=["market"])


def _series_points(
    candles: list[Candle],
    values: list[float],
    *,
    precision: int = 4,
) -> list[dict[str, float | int]]:
    if not candles or not values:
        return []

    aligned_candles = candles[-len(values) :]
    return [
        {
            "open_time": candle.open_time,
            "value": round(float(value), precision),
        }
        for candle, value in zip(aligned_candles, values)
    ]


def _latest_value(values: list[float], *, precision: int = 4) -> float | None:
    if not values:
        return None
    return round(float(values[-1]), precision)


def _build_indicator_payload(
    symbol: str,
    interval: str,
    candles: list[Candle],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    indicators = compute_indicators(closes, config=config, highs=highs, lows=lows, volumes=volumes)

    macd_line, macd_signal, macd_histogram = indicators.get("macd", ([], [], []))
    bb_upper, bb_middle, bb_lower = indicators.get("bollinger_bands", ([], [], []))

    resolved_config = {
        "sma_short": int((config or {}).get("sma_short", 20)),
        "sma_long": int((config or {}).get("sma_long", 50)),
        "rsi_period": int((config or {}).get("rsi_period", 14)),
        "volume_ma_period": int((config or {}).get("volume_ma_period", 20)),
    }

    return {
        "symbol": symbol,
        "interval": interval,
        "candles_used": len(candles),
        "config": resolved_config,
        "latest": {
            "price": round(float(closes[-1]), 4) if closes else None,
            "rsi": _latest_value(indicators.get("rsi", []), precision=2),
            "atr": _latest_value(indicators.get("atr", []), precision=4),
            "adx": _latest_value(indicators.get("adx", []), precision=2),
            "volume_ratio": _latest_value(indicators.get("volume_ratio", []), precision=3),
            "macd_line": _latest_value(macd_line),
            "macd_signal": _latest_value(macd_signal),
            "macd_histogram": _latest_value(macd_histogram),
        },
        "series": {
            "sma_short": _series_points(candles, indicators.get("sma_short", [])),
            "sma_long": _series_points(candles, indicators.get("sma_long", [])),
            "ema_12": _series_points(candles, indicators.get("ema_12", [])),
            "ema_26": _series_points(candles, indicators.get("ema_26", [])),
            "bollinger_upper": _series_points(candles, bb_upper),
            "bollinger_middle": _series_points(candles, bb_middle),
            "bollinger_lower": _series_points(candles, bb_lower),
            "rsi": _series_points(candles, indicators.get("rsi", []), precision=2),
            "macd_line": _series_points(candles, macd_line),
            "macd_signal": _series_points(candles, macd_signal),
            "macd_histogram": _series_points(candles, macd_histogram),
            "atr": _series_points(candles, indicators.get("atr", [])),
            "adx": _series_points(candles, indicators.get("adx", []), precision=2),
            "volume_ratio": _series_points(candles, indicators.get("volume_ratio", []), precision=3),
        },
    }


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


@router.get("/indicators/{symbol}")
async def get_indicator_series(
    symbol: str,
    interval: str = Query("1h"),
    limit: int = Query(200, ge=1, le=500),
    sma_short: int | None = Query(None, ge=1, le=200),
    sma_long: int | None = Query(None, ge=2, le=400),
    rsi_period: int | None = Query(None, ge=2, le=100),
    volume_ma_period: int | None = Query(None, ge=2, le=200),
):
    store = DataStore.get_instance()
    candles = store.get_candles(symbol.upper(), interval, limit)
    if not candles:
        raise HTTPException(404, f"No candle data for {symbol}")

    config = {
        key: value
        for key, value in {
            "sma_short": sma_short,
            "sma_long": sma_long,
            "rsi_period": rsi_period,
            "volume_ma_period": volume_ma_period,
        }.items()
        if value is not None
    }

    return _build_indicator_payload(symbol.upper(), interval, candles, config)


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


@router.get("/regime/{symbol}")
async def get_regime(
    symbol: str,
    interval: str = Query("1h"),
):
    """Return the current market regime classification for a symbol."""
    store = DataStore.get_instance()
    candles = store.get_candles(symbol.upper(), interval, 200)
    if len(candles) < 50:
        raise HTTPException(400, f"Not enough candle data ({len(candles)}/50)")

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    indicators = compute_indicators(closes, highs=highs, lows=lows, volumes=volumes)
    classifier = RegimeClassifier()
    result = classifier.classify(indicators)

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "regime": result.regime.value,
        "confidence": round(result.confidence, 3),
        "reasoning": result.reasoning,
        "metrics": result.metrics,
        "candles_used": len(candles),
    }
