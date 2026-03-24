"""Dashboard and leaderboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.ai_call_log import AICallLog
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.schemas.dashboard import DashboardResponse, EquityPoint, LeaderboardEntry
from app.api.strategies import _build_stats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    strategies = result.scalars().all()

    stats_list = [await _build_stats(session, s) for s in strategies]
    active = sum(1 for s in stats_list if s.is_active)
    ai_enabled = sum(1 for s in stats_list if s.ai_enabled)

    # Get actual API call counts from logs table (excludes skipped/cooldown)
    actual_calls = (await session.execute(
        select(func.count()).select_from(AICallLog).where(
            AICallLog.status.in_(["success", "signal", "hold"])
        )
    )).scalar() or 0
    total_log_cost = (await session.execute(
        select(func.sum(AICallLog.cost_usdt)).where(
            AICallLog.status.in_(["success", "signal", "hold"])
        )
    )).scalar()
    ai_total_cost_usdt = round(float(total_log_cost or 0), 8)

    return DashboardResponse(
        strategies=stats_list,
        total_strategies=len(stats_list),
        active_strategies=active,
        ai_enabled_strategies=ai_enabled,
        ai_total_calls=actual_calls,
        ai_total_cost_usdt=ai_total_cost_usdt,
    )


@router.get("/dashboard/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    sort_by: str = Query("total_pnl", pattern="^(total_pnl|win_rate|total_trades|total_equity)$"),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    strategies = result.scalars().all()

    entries = []
    for s in strategies:
        stats = await _build_stats(session, s)
        entries.append(
            LeaderboardEntry(
                strategy_id=s.id,
                strategy_name=s.name,
                total_pnl=stats.total_pnl,
                unrealized_pnl=stats.unrealized_pnl,
                has_open_position=stats.has_open_position,
                win_rate=stats.win_rate,
                total_trades=stats.total_trades,
                total_equity=stats.total_equity or 0.0,
                ai_enabled=stats.ai_enabled,
                ai_total_calls=stats.ai_total_calls,
                ai_total_cost_usdt=stats.ai_total_cost_usdt,
                rank=0,
            )
        )

    # Sort
    reverse = True
    entries.sort(key=lambda e: getattr(e, sort_by), reverse=reverse)
    for i, entry in enumerate(entries):
        entry.rank = i + 1

    return entries


@router.get("/strategies/{strategy_id}/equity-curve", response_model=list[EquityPoint])
async def get_equity_curve(
    strategy_id: str,
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
):
    # Verify strategy exists
    s = await session.execute(select(Strategy.id).where(Strategy.id == strategy_id))
    if s.scalar_one_or_none() is None:
        raise HTTPException(404, "Strategy not found")

    result = await session.execute(
        select(Snapshot)
        .where(Snapshot.strategy_id == strategy_id)
        .order_by(Snapshot.timestamp.desc())
        .limit(limit)
    )
    snapshots = list(reversed(result.scalars().all()))
    return [
        EquityPoint(
            timestamp=snap.timestamp,
            total_equity_usdt=float(snap.total_equity_usdt),
        )
        for snap in snapshots
    ]
