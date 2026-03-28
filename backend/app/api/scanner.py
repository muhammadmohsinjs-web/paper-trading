"""Opportunity scanner API endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from app.config import get_settings
from app.scanner.scanner import OpportunityScanner
from app.scanner.universe_selector import UniverseSelector

router = APIRouter(prefix="/scanner", tags=["scanner"])
settings = get_settings()


@router.get("/opportunities")
async def get_opportunities(
    interval: str = Query("1h"),
    max_results: int = Query(5, ge=1, le=20),
):
    """Scan all configured symbols for trading opportunities.

    Returns ranked setups sorted by score. Uses dynamic universe if enabled.
    """
    scanner = OpportunityScanner()
    await scanner.resolve_symbols()
    result = scanner.scan(interval=interval, max_results=max_results)

    return {
        "scanned_at": result.scanned_at,
        "symbols_scanned": result.symbols_scanned,
        "regime": result.regime,
        "dynamic_universe_enabled": settings.dynamic_universe_enabled,
        "opportunities": [asdict(s) for s in result.opportunities],
    }


@router.post("/scan")
async def run_manual_scan(
    interval: str = Query("1h"),
    max_results: int = Query(10, ge=1, le=30),
):
    """Run a full market scan now and return ranked symbols.

    Uses dynamic universe selection if enabled, otherwise falls back
    to the static list.
    """
    scanner = OpportunityScanner()
    await scanner.resolve_symbols()
    ranked = scanner.rank_symbols(
        interval=interval,
        max_results=max_results,
        liquidity_floor_usdt=settings.multi_coin_liquidity_floor_usdt,
    )

    scan_result = scanner.scan(interval=interval, max_results=max_results)

    # Build filtration funnel stats
    selector = UniverseSelector.get_instance()
    snapshot = selector.get_last_snapshot()
    rank_stats = scanner.get_rank_funnel_stats()
    total_symbols = len(scanner.symbols)

    funnel = {
        "total_usdt_pairs": snapshot.total_usdt_pairs if snapshot else 0,
        "after_hard_filters": snapshot.candidate_pool_size if snapshot else total_symbols,
        "after_tradability": (snapshot.candidate_pool_size - snapshot.tradability_failed_count) if snapshot else 0,
        "active_universe": total_symbols,
        "with_data": total_symbols - rank_stats["no_data"],
        "after_setup_detection": total_symbols - rank_stats["no_data"] - rank_stats["tradability_rejected"] - rank_stats["no_setup"],
        "after_liquidity_floor": total_symbols - rank_stats["no_data"] - rank_stats["tradability_rejected"] - rank_stats["no_setup"] - rank_stats["low_liquidity"],
        "final_ranked": len(ranked),
    }

    # Collect per-symbol audit data for the detail page
    audit_rows = scanner.get_last_rank_audit()
    candidate_evaluations = (
        [asdict(c) for c in snapshot.candidate_evaluations] if snapshot else []
    )

    return {
        "scanned_at": scan_result.scanned_at,
        "symbols_scanned": scan_result.symbols_scanned,
        "regime": scan_result.regime,
        "universe_size": len(scanner.symbols),
        "dynamic_universe_enabled": settings.dynamic_universe_enabled,
        "ranked_symbols": [asdict(s) for s in ranked],
        "opportunities": [asdict(s) for s in scan_result.opportunities],
        "funnel": funnel,
        "audit_rows": audit_rows,
        "candidate_evaluations": candidate_evaluations,
    }


@router.get("/universe")
async def get_universe_status():
    """Return the current dynamic universe state.

    Shows candidate pool size, active universe, promoted/demoted coins,
    and activity scores for each selected coin.
    """
    selector = UniverseSelector.get_instance()
    snapshot = selector.get_last_snapshot()

    if snapshot is None:
        return {
            "status": "not_initialized",
            "dynamic_universe_enabled": settings.dynamic_universe_enabled,
            "fallback_universe_size": len(settings.default_scan_universe),
        }

    return {
        "status": "active",
        "dynamic_universe_enabled": settings.dynamic_universe_enabled,
        "timestamp": snapshot.timestamp,
        "candidate_pool_size": snapshot.candidate_pool_size,
        "active_universe_size": snapshot.active_universe_size,
        "active_symbols": snapshot.active_symbols,
        "promoted": snapshot.promoted,
        "demoted": snapshot.demoted,
        "scores": [asdict(s) for s in snapshot.scores],
    }


@router.post("/universe/refresh")
async def refresh_universe():
    """Force-refresh the dynamic universe immediately."""
    selector = UniverseSelector.get_instance()
    symbols = await selector.get_active_universe(force_refresh=True)
    snapshot = selector.get_last_snapshot()

    return {
        "status": "refreshed",
        "active_universe_size": len(symbols),
        "active_symbols": symbols,
        "promoted": snapshot.promoted if snapshot else [],
        "demoted": snapshot.demoted if snapshot else [],
    }
