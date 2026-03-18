"""Engine control endpoints — start/stop all strategies, manual trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.engine.trading_loop import run_single_cycle
from app.models.strategy import Strategy
from app.strategies.manager import StrategyManager

router = APIRouter(prefix="/engine", tags=["engine"])


@router.post("/start")
async def start_engine():
    manager = StrategyManager.get_instance()
    count = await manager.start_all_active()
    return {"status": "started", "strategies_started": count}


@router.post("/stop")
async def stop_engine():
    manager = StrategyManager.get_instance()
    count = await manager.stop_all()
    return {"status": "stopped", "strategies_stopped": count}


@router.get("/status")
async def engine_status():
    manager = StrategyManager.get_instance()
    running = manager.running_strategies()
    return {"running_strategies": running, "count": len(running)}


@router.post("/strategies/{strategy_id}/execute")
async def manual_execute(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Manually trigger one strategy decision cycle."""
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    trade_info = await run_single_cycle(strategy_id)
    if trade_info is None:
        return {"status": "hold", "message": "No trade signal or insufficient data"}
    return {"status": "executed", "trade": trade_info}
