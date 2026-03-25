"""Opportunity scanner API endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from app.scanner.scanner import OpportunityScanner

router = APIRouter(prefix="/scanner", tags=["scanner"])


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
