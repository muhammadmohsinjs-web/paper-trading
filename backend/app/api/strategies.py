"""Strategy CRUD endpoints."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db_session
from app.models.enums import TradeSide
from app.models.position import Position
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.wallet import Wallet
from app.schemas.strategy import (
    StrategyCreate,
    StrategyResponse,
    StrategyUpdate,
    StrategyWithStats,
)
from app.schemas.wallet import PositionResponse, WalletResponse
from app.market.data_store import DataStore
from app.strategies.manager import StrategyManager

router = APIRouter(prefix="/strategies", tags=["strategies"])


async def _build_stats(session: AsyncSession, strategy: Strategy) -> StrategyWithStats:
    """Build a StrategyWithStats from DB data."""
    # Wallet
    wallet_result = await session.execute(
        select(Wallet).where(Wallet.strategy_id == strategy.id)
    )
    wallet = wallet_result.scalar_one_or_none()

    # Trade stats
    trade_result = await session.execute(
        select(
            func.count(Trade.id),
            func.count(Trade.pnl).filter(Trade.pnl > 0),
            func.coalesce(func.sum(Trade.pnl), 0),
        ).where(Trade.strategy_id == strategy.id, Trade.side == TradeSide.SELL)
    )
    row = trade_result.one()
    sell_count, winning, total_pnl = int(row[0]), int(row[1]), float(row[2])

    total_trade_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.strategy_id == strategy.id)
    )
    total_trades = total_trade_result.scalar() or 0

    # Equity estimate
    store = DataStore.get_instance()
    price = store.get_latest_price("BTCUSDT")
    position_result = await session.execute(
        select(Position).where(Position.strategy_id == strategy.id)
    )
    position = position_result.scalar_one_or_none()

    total_equity = float(wallet.available_usdt) if wallet else 0.0
    if position and price:
        total_equity += float(position.quantity) * price

    return StrategyWithStats(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        config_json=strategy.config_json or {},
        is_active=strategy.is_active,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
        available_usdt=float(wallet.available_usdt) if wallet else None,
        initial_balance_usdt=float(wallet.initial_balance_usdt) if wallet else None,
        total_equity=total_equity,
        total_trades=total_trades,
        winning_trades=winning,
        total_pnl=total_pnl,
        win_rate=round(winning / sell_count * 100, 2) if sell_count else 0.0,
    )


@router.get("", response_model=list[StrategyWithStats])
async def list_strategies(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    strategies = result.scalars().all()
    return [await _build_stats(session, s) for s in strategies]


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    body: StrategyCreate,
    session: AsyncSession = Depends(get_db_session),
):
    strategy = Strategy(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        config_json=body.config_json,
        is_active=body.is_active,
    )
    session.add(strategy)

    # Create wallet
    initial = Decimal(str(body.config_json.get("initial_balance", 1000)))
    wallet = Wallet(
        id=str(uuid4()),
        strategy_id=strategy.id,
        initial_balance_usdt=initial,
        available_usdt=initial,
    )
    session.add(wallet)
    await session.commit()
    await session.refresh(strategy)

    # Auto-start if active
    if strategy.is_active:
        interval = body.config_json.get("interval_seconds", 300)
        await StrategyManager.get_instance().start_strategy(strategy.id, interval)

    return strategy


@router.get("/{strategy_id}", response_model=StrategyWithStats)
async def get_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")
    return await _build_stats(session, strategy)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdate,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(strategy, key, value)

    # Handle start/stop
    manager = StrategyManager.get_instance()
    if "is_active" in updates:
        if body.is_active:
            interval = (strategy.config_json or {}).get("interval_seconds", 300)
            await manager.start_strategy(strategy.id, interval)
        else:
            await manager.stop_strategy(strategy.id)

    await session.commit()
    await session.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    await StrategyManager.get_instance().stop_strategy(strategy_id)
    await session.delete(strategy)
    await session.commit()
