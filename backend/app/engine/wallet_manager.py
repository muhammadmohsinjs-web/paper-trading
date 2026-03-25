"""Wallet and position management for paper trading."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PositionSide
from app.models.position import Position
from app.models.wallet import Wallet


async def get_or_create_wallet(
    session: AsyncSession,
    strategy_id: str,
    initial_balance: Decimal = Decimal("1000"),
) -> Wallet:
    result = await session.execute(
        select(Wallet).where(Wallet.strategy_id == strategy_id)
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(
            id=str(uuid4()),
            strategy_id=strategy_id,
            initial_balance_usdt=initial_balance,
            available_usdt=initial_balance,
            peak_equity_usdt=initial_balance,
        )
        session.add(wallet)
        await session.flush()
    return wallet


async def debit_wallet(
    session: AsyncSession,
    wallet: Wallet,
    amount: Decimal,
) -> None:
    """Subtract amount from available USDT. Raises ValueError if insufficient."""
    if wallet.available_usdt < amount:
        raise ValueError(
            f"Insufficient balance: have {wallet.available_usdt}, need {amount}"
        )
    wallet.available_usdt = wallet.available_usdt - amount
    await session.flush()


async def credit_wallet(
    session: AsyncSession,
    wallet: Wallet,
    amount: Decimal,
) -> None:
    """Add amount to available USDT."""
    wallet.available_usdt = wallet.available_usdt + amount
    await session.flush()


async def open_position(
    session: AsyncSession,
    strategy_id: str,
    symbol: str,
    quantity: Decimal,
    entry_price: Decimal,
    entry_fee: Decimal,
    *,
    entry_confidence_raw: Decimal | None = None,
    entry_confidence_final: Decimal | None = None,
    entry_confidence_bucket: str | None = None,
) -> Position:
    """Create a new LONG position."""
    position = Position(
        id=str(uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=quantity,
        entry_price=entry_price,
        entry_fee=entry_fee,
        entry_confidence_raw=entry_confidence_raw,
        entry_confidence_final=entry_confidence_final,
        entry_confidence_bucket=entry_confidence_bucket,
    )
    session.add(position)
    await session.flush()
    return position


async def get_position(
    session: AsyncSession,
    strategy_id: str,
    symbol: str,
) -> Position | None:
    result = await session.execute(
        select(Position).where(
            Position.strategy_id == strategy_id,
            Position.symbol == symbol,
        )
    )
    return result.scalar_one_or_none()


async def close_position(
    session: AsyncSession,
    position: Position,
) -> None:
    """Remove a position (fully closed)."""
    await session.delete(position)
    await session.flush()
