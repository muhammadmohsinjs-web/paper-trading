"""Opportunity scanner API endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from app.config import get_settings
from app.scanner.scanner import OpportunityScanner

router = APIRouter(prefix="/scanner", tags=["scanner"])
settings = get_settings()


@router.get("/opportunities")
async def get_opportunities(
    interval: str = Query("1h"),
    max_results: int = Query(5, ge=1, le=20),
):
    """Scan all configured symbols for trading opportunities.

    Returns ranked setups sorted by score. Only symbols with sufficient
    candle data in the DataStore will be included.
    """
    scanner = OpportunityScanner()
    result = scanner.scan(interval=interval, max_results=max_results)

    return {
        "scanned_at": result.scanned_at,
        "symbols_scanned": result.symbols_scanned,
        "regime": result.regime,
        "opportunities": [asdict(s) for s in result.opportunities],
    }


@router.post("/scan")
async def run_manual_scan(
    interval: str = Query("1h"),
    max_results: int = Query(10, ge=1, le=30),
):
    """Run a full market scan now and return ranked symbols.

    This performs a fresh scan using rank_symbols (the same logic used
    for daily pick selection) and returns results immediately without
    persisting them. Use this for on-demand market exploration.
    """
    scanner = OpportunityScanner()
    ranked = scanner.rank_symbols(
        interval=interval,
        max_results=max_results,
        liquidity_floor_usdt=settings.multi_coin_liquidity_floor_usdt,
    )

    # Also get the raw scan for opportunity details
    scan_result = scanner.scan(interval=interval, max_results=max_results)

    return {
        "scanned_at": scan_result.scanned_at,
        "symbols_scanned": scan_result.symbols_scanned,
        "regime": scan_result.regime,
        "universe_size": len(scanner.symbols),
        "ranked_symbols": [asdict(s) for s in ranked],
        "opportunities": [asdict(s) for s in scan_result.opportunities],
    }
