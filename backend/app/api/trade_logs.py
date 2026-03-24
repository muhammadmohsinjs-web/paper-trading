"""Cross-strategy trade log endpoints — view buy/sell logs for all strategies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.enums import TradeSide
from app.models.trade import Trade
from app.schemas.trade import TradeLogResponse, TradeResponse

router = APIRouter(prefix="/trade-logs", tags=["trade-logs"])


@router.get("", response_model=TradeLogResponse)
async def list_trade_logs(
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    side: str | None = Query(None, description="Filter by side: BUY or SELL"),
    decision_source: str | None = Query(None, description="Filter by decision source: rule, ai, hybrid_entry, hybrid_exit, risk"),
    strategy_type: str | None = Query(None, description="Filter by strategy type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    """List trade logs across all strategies with optional filters."""
    query = select(Trade)
    count_query = select(func.count(Trade.id))

    if strategy_id:
        query = query.where(Trade.strategy_id == strategy_id)
        count_query = count_query.where(Trade.strategy_id == strategy_id)
    if side:
        trade_side = TradeSide.BUY if side.upper() == "BUY" else TradeSide.SELL
        query = query.where(Trade.side == trade_side)
        count_query = count_query.where(Trade.side == trade_side)
    if decision_source:
        query = query.where(Trade.decision_source == decision_source)
        count_query = count_query.where(Trade.decision_source == decision_source)
    if strategy_type:
        query = query.where(Trade.strategy_type == strategy_type)
        count_query = count_query.where(Trade.strategy_type == strategy_type)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(
        query.order_by(Trade.executed_at.desc()).limit(limit).offset(offset)
    )
    trades = result.scalars().all()

    return TradeLogResponse(
        total=total,
        offset=offset,
        limit=limit,
        trades=[TradeResponse.model_validate(t) for t in trades],
    )
