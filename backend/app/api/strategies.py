"""Strategy CRUD endpoints."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db_session
from app.models.enums import TradeSide
from app.models.position import Position
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.wallet import Wallet
from app.schemas.wallet import PositionResponse, WalletResponse
from app.schemas.strategy import (
    StrategyCreate,
    StrategyResponse,
    StrategyUpdate,
    StrategyWithStats,
)
from app.market.data_store import DataStore
from app.strategies.manager import StrategyManager

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _strategy_ai_defaults(strategy: Strategy) -> dict[str, object]:
    config = strategy.config_json or {}
    return {
        "ai_enabled": bool(strategy.ai_enabled or config.get("ai_enabled", False)),
        "ai_strategy_key": strategy.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type"),
        "ai_model": strategy.ai_model or config.get("ai_model"),
        "ai_cooldown_seconds": int(strategy.ai_cooldown_seconds or config.get("ai_cooldown_seconds") or 60),
        "ai_max_tokens": int(strategy.ai_max_tokens or config.get("ai_max_tokens") or 700),
        "ai_temperature": float(strategy.ai_temperature),
        "ai_last_decision_at": strategy.ai_last_decision_at,
        "ai_last_decision_status": strategy.ai_last_decision_status,
        "ai_last_reasoning": strategy.ai_last_reasoning,
        "ai_last_model": strategy.ai_last_model,
        "ai_last_prompt_tokens": strategy.ai_last_prompt_tokens,
        "ai_last_completion_tokens": strategy.ai_last_completion_tokens,
        "ai_last_total_tokens": strategy.ai_last_total_tokens,
        "ai_last_cost_usdt": float(strategy.ai_last_cost_usdt),
        "ai_total_calls": strategy.ai_total_calls,
        "ai_total_prompt_tokens": strategy.ai_total_prompt_tokens,
        "ai_total_completion_tokens": strategy.ai_total_completion_tokens,
        "ai_total_tokens": strategy.ai_total_tokens,
        "ai_total_cost_usdt": float(strategy.ai_total_cost_usdt),
    }


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
        **_strategy_ai_defaults(strategy),
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
    config_json = body.config_json or {}
    strategy = Strategy(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        config_json=config_json,
        is_active=body.is_active,
        ai_enabled=body.ai_enabled or bool(config_json.get("ai_enabled", False)),
        ai_strategy_key=body.ai_strategy_key or config_json.get("ai_strategy_key") or config_json.get("strategy_type"),
        ai_model=body.ai_model or config_json.get("ai_model"),
        ai_cooldown_seconds=body.ai_cooldown_seconds or config_json.get("ai_cooldown_seconds") or 60,
        ai_max_tokens=body.ai_max_tokens or config_json.get("ai_max_tokens") or 700,
        ai_temperature=Decimal(
            str(
                body.ai_temperature
                if body.ai_temperature is not None
                else config_json.get("ai_temperature", 0.2)
            )
        ),
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
        interval = config_json.get("interval_seconds", 300)
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


@router.get("/{strategy_id}/wallet", response_model=WalletResponse)
async def get_strategy_wallet(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    wallet_result = await session.execute(
        select(Wallet).where(Wallet.strategy_id == strategy_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(404, "Wallet not found")
    return wallet


@router.get("/{strategy_id}/positions", response_model=list[PositionResponse])
async def get_strategy_positions(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    strategy_result = await session.execute(
        select(Strategy.id).where(Strategy.id == strategy_id)
    )
    if strategy_result.scalar_one_or_none() is None:
        raise HTTPException(404, "Strategy not found")

    result = await session.execute(
        select(Position).where(Position.strategy_id == strategy_id).order_by(Position.opened_at.desc())
    )
    positions = result.scalars().all()
    store = DataStore.get_instance()

    return [
        PositionResponse(
            id=position.id,
            strategy_id=position.strategy_id,
            symbol=position.symbol,
            side=position.side,
            quantity=float(position.quantity),
            entry_price=float(position.entry_price),
            entry_fee=float(position.entry_fee),
            opened_at=position.opened_at,
            current_price=store.get_latest_price(position.symbol),
            unrealized_pnl=(
                (float(store.get_latest_price(position.symbol)) - float(position.entry_price))
                * float(position.quantity)
                - float(position.entry_fee)
            )
            if store.get_latest_price(position.symbol) is not None
            else None,
        )
        for position in positions
    ]


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

    config = strategy.config_json or {}
    if "ai_enabled" in updates and body.ai_enabled is not None:
        strategy.ai_enabled = body.ai_enabled
    if "ai_strategy_key" in updates:
        strategy.ai_strategy_key = body.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type")
    if "ai_model" in updates:
        strategy.ai_model = body.ai_model or config.get("ai_model")
    if "ai_cooldown_seconds" in updates and body.ai_cooldown_seconds is not None:
        strategy.ai_cooldown_seconds = body.ai_cooldown_seconds
    if "ai_max_tokens" in updates and body.ai_max_tokens is not None:
        strategy.ai_max_tokens = body.ai_max_tokens
    if "ai_temperature" in updates and body.ai_temperature is not None:
        strategy.ai_temperature = Decimal(str(body.ai_temperature))

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
