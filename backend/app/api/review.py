"""Review system API endpoints."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, commit_with_write_lock, get_db_session
from app.models.review_ledger import ReviewForwardOutcome, ReviewLedger
from app.review.report_generator import REPORTS_DIR, generate_daily_report, generate_weekly_report

router = APIRouter(prefix="/review", tags=["review"])


# ── Ledger endpoints ──────────────────────────────────────────────────

@router.get("/ledger")
async def list_ledger(
    strategy_id: Optional[str] = Query(None),
    cycle_id: Optional[str] = Query(None),
    outcome_bucket: Optional[str] = Query(None),
    root_cause: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    query = select(ReviewLedger).outerjoin(
        ReviewForwardOutcome, ReviewForwardOutcome.ledger_id == ReviewLedger.id
    )

    if strategy_id:
        query = query.where(ReviewLedger.strategy_id == strategy_id)
    if cycle_id:
        query = query.where(ReviewLedger.cycle_id == cycle_id)
    if outcome_bucket:
        query = query.where(ReviewLedger.outcome_bucket == outcome_bucket)
    if root_cause:
        query = query.where(ReviewLedger.root_cause == root_cause)
    if date_from:
        dt = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
        query = query.where(ReviewLedger.cycle_ts >= dt)
    if date_to:
        dt = datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc)
        query = query.where(ReviewLedger.cycle_ts <= dt)

    query = query.order_by(ReviewLedger.cycle_ts.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    rows = result.scalars().all()

    return {
        "total": len(rows),
        "offset": offset,
        "items": [_ledger_to_dict(r) for r in rows],
    }


@router.get("/ledger/{ledger_id}")
async def get_ledger_entry(
    ledger_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    result = await session.execute(
        select(ReviewLedger)
        .outerjoin(ReviewForwardOutcome, ReviewForwardOutcome.ledger_id == ReviewLedger.id)
        .where(ReviewLedger.id == ledger_id)
        .add_columns(ReviewForwardOutcome)
    )
    row = result.first()
    if row is None:
        raise HTTPException(404, "Ledger entry not found")
    entry, outcome = row
    d = _ledger_to_dict(entry)
    if outcome:
        d["forward_outcome"] = _outcome_to_dict(outcome)
    return d


@router.get("/summary")
async def review_summary(
    strategy_id: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(ReviewLedger).where(ReviewLedger.cycle_ts >= since)
    if strategy_id:
        query = query.where(ReviewLedger.strategy_id == strategy_id)

    result = await session.execute(query)
    rows = result.scalars().all()

    buckets: dict[str, int] = {}
    causes: dict[str, int] = {}
    for r in rows:
        b = r.outcome_bucket or "unclassified"
        buckets[b] = buckets.get(b, 0) + 1
        if r.root_cause and r.root_cause != "none":
            causes[r.root_cause] = causes.get(r.root_cause, 0) + 1

    traded = [r for r in rows if r.trade_opened]
    closed = [r for r in traded if r.trade_closed]
    pnls = [r.realized_pnl_pct for r in closed if r.realized_pnl_pct is not None]

    return {
        "period_days": days,
        "total_symbols_evaluated": len(rows),
        "outcome_buckets": buckets,
        "root_causes": causes,
        "trades_opened": len(traded),
        "trades_closed": len(closed),
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 3) if pnls else None,
        "win_rate": round(sum(1 for p in pnls if p > 0) / len(pnls), 3) if pnls else None,
    }


# ── Manual trigger endpoints ──────────────────────────────────────────

@router.post("/run/forward-labeler")
async def trigger_forward_labeler(
    background_tasks: BackgroundTasks,
    strategy_id: Optional[str] = Query(None),
) -> dict[str, str]:
    async def _job() -> None:
        from app.review.forward_labeler import label_forward_outcomes
        async with SessionLocal() as session:
            n = await label_forward_outcomes(session, strategy_id=strategy_id, limit=2000)
            await commit_with_write_lock(session)

    background_tasks.add_task(_job)
    return {"status": "started"}


@router.post("/run/classifier")
async def trigger_classifier(
    background_tasks: BackgroundTasks,
    strategy_id: Optional[str] = Query(None),
) -> dict[str, str]:
    async def _job() -> None:
        from app.review.outcome_classifier import classify_pending
        async with SessionLocal() as session:
            n = await classify_pending(session, strategy_id=strategy_id, limit=2000)
            await commit_with_write_lock(session)

    background_tasks.add_task(_job)
    return {"status": "started"}


# ── Report endpoints ──────────────────────────────────────────────────

@router.get("/reports")
async def list_reports() -> dict[str, Any]:
    """List all generated reports by reading .meta.json sidecars."""
    reports: list[dict[str, Any]] = []
    for subdir in ("daily", "weekly"):
        folder = REPORTS_DIR / subdir
        if not folder.exists():
            continue
        for meta_file in sorted(folder.glob("*.meta.json"), reverse=True):
            try:
                meta = json.loads(meta_file.read_text())
                meta["subtype"] = subdir
                reports.append(meta)
            except Exception:
                continue
    return {"reports": reports}


@router.get("/reports/{report_type}/{label}")
async def get_report(report_type: str, label: str) -> dict[str, Any]:
    """
    Get a specific report. report_type is 'daily' or 'weekly'.
    label is YYYY-MM-DD for daily or YYYY-WXX for weekly.
    """
    if report_type not in ("daily", "weekly"):
        raise HTTPException(400, "report_type must be 'daily' or 'weekly'")

    folder = REPORTS_DIR / report_type
    md_path = folder / f"{label}.md"
    meta_path = folder / f"{label}.meta.json"

    if not md_path.exists():
        raise HTTPException(404, f"Report {report_type}/{label} not found")

    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    content = md_path.read_text(encoding="utf-8")

    return {"label": label, "type": report_type, "meta": meta, "content": content}


@router.post("/reports/generate/daily")
async def trigger_daily_report(
    background_tasks: BackgroundTasks,
    target_date: Optional[date] = Query(None, description="YYYY-MM-DD, defaults to yesterday"),
) -> dict[str, str]:
    async def _job() -> None:
        await generate_daily_report(date=target_date)

    background_tasks.add_task(_job)
    return {"status": "started", "date": str(target_date or "yesterday")}


@router.post("/reports/generate/weekly")
async def trigger_weekly_report(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(generate_weekly_report)
    return {"status": "started"}


# ── Serializers ───────────────────────────────────────────────────────

def _ledger_to_dict(e: ReviewLedger) -> dict[str, Any]:
    return {
        "id": e.id,
        "strategy_id": e.strategy_id,
        "cycle_id": e.cycle_id,
        "cycle_ts": e.cycle_ts.isoformat() if e.cycle_ts else None,
        "symbol": e.symbol,
        "interval": e.interval,
        "in_universe": e.in_universe,
        "tradability_pass": e.tradability_pass,
        "data_sufficient": e.data_sufficient,
        "setup_detected": e.setup_detected,
        "setup_type": e.setup_type,
        "setup_family": e.setup_family,
        "liquidity_pass": e.liquidity_pass,
        "final_gate_pass": e.final_gate_pass,
        "rejection_stage": e.rejection_stage,
        "rejection_reason_code": e.rejection_reason_code,
        "rejection_reason_text": e.rejection_reason_text,
        "daily_pick_rank": e.daily_pick_rank,
        "scanner_score": e.scanner_score,
        "regime_at_decision": e.regime_at_decision,
        "universe_size": e.universe_size,
        "rank_among_qualified": e.rank_among_qualified,
        "ai_called": e.ai_called,
        "ai_action": e.ai_action,
        "ai_confidence": e.ai_confidence,
        "ai_status": e.ai_status,
        "trade_opened": e.trade_opened,
        "entry_price": e.entry_price,
        "slippage_pct": e.slippage_pct,
        "position_size_usdt": e.position_size_usdt,
        "exposure_pct": e.exposure_pct,
        "composite_score": e.composite_score,
        "entry_confidence": e.entry_confidence,
        "confidence_bucket": e.confidence_bucket,
        "decision_source": e.decision_source,
        "no_execute_reason": e.no_execute_reason,
        "trade_closed": e.trade_closed,
        "realized_pnl_pct": e.realized_pnl_pct,
        "realized_pnl_usdt": e.realized_pnl_usdt,
        "exit_reason": e.exit_reason,
        "hold_duration_hours": e.hold_duration_hours,
        "position_still_open": e.position_still_open,
        "outcome_bucket": e.outcome_bucket,
        "root_cause": e.root_cause,
        "root_cause_confidence": e.root_cause_confidence,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _outcome_to_dict(o: ReviewForwardOutcome) -> dict[str, Any]:
    return {
        "fwd_ret_1": o.fwd_ret_1,
        "fwd_ret_4": o.fwd_ret_4,
        "fwd_ret_12": o.fwd_ret_12,
        "fwd_ret_24": o.fwd_ret_24,
        "fwd_max_favorable_pct": o.fwd_max_favorable_pct,
        "fwd_max_adverse_pct": o.fwd_max_adverse_pct,
        "fwd_data_available": o.fwd_data_available,
        "computed_at": o.computed_at.isoformat() if o.computed_at else None,
    }
