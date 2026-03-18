"""Trade history and summary endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.enums import TradeSide
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.schemas.trade import TradeResponse, TradeSummary

router = APIRouter(prefix="/strategies/{strategy_id}/trades", tags=["trades"])


@router.get("", response_model=list[TradeResponse])
async def list_trades(
    strategy_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    # Verify strategy exists
    s = await session.execute(select(Strategy.id).where(Strategy.id == strategy_id))
    if s.scalar_one_or_none() is None:
        raise HTTPException(404, "Strategy not found")

    result = await session.execute(
        select(Trade)
        .where(Trade.strategy_id == strategy_id)
        .order_by(Trade.executed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/summary", response_model=TradeSummary)
async def trade_summary(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    # Verify strategy exists
    s = await session.execute(select(Strategy.id).where(Strategy.id == strategy_id))
    if s.scalar_one_or_none() is None:
        raise HTTPException(404, "Strategy not found")

    # Total counts
    total_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.strategy_id == strategy_id)
    )
    total_trades = total_result.scalar() or 0

    buy_result = await session.execute(
        select(func.count(Trade.id)).where(
            Trade.strategy_id == strategy_id, Trade.side == TradeSide.BUY
        )
    )
    buy_count = buy_result.scalar() or 0

    # Sell trades with P&L
    sell_result = await session.execute(
        select(Trade.pnl)
        .where(Trade.strategy_id == strategy_id, Trade.side == TradeSide.SELL)
    )
    pnls = [float(row[0]) for row in sell_result.all() if row[0] is not None]

    sell_count = len(pnls)
    winning = sum(1 for p in pnls if p > 0)
    losing = sum(1 for p in pnls if p <= 0)
    total_pnl = sum(pnls) if pnls else 0.0

    return TradeSummary(
        total_trades=total_trades,
        buy_count=buy_count,
        sell_count=sell_count,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=round(winning / sell_count * 100, 2) if sell_count else 0.0,
        total_pnl=round(total_pnl, 8),
        avg_pnl=round(total_pnl / sell_count, 8) if sell_count else 0.0,
        best_trade=max(pnls) if pnls else 0.0,
        worst_trade=min(pnls) if pnls else 0.0,
    )
