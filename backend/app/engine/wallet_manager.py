"""Wallet and position management for paper trading."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import flush_with_write_lock
from app.models.enums import PositionSide
from app.models.position import Position
from app.models.wallet import Wallet


async def get_or_create_wallet(
    session: AsyncSession,
    strategy_id: str,
    initial_balance: Decimal = Decimal("1000"),
) -> Wallet:
    settings = get_settings()

    # Shared wallet mode: all strategies use a single wallet
    if settings.shared_wallet_enabled:
        result = await session.execute(
            select(Wallet).order_by(Wallet.initial_balance_usdt.desc()).limit(1)
        )
        wallet = result.scalar_one_or_none()
        if wallet is not None:
            return wallet
        # First call — create the shared wallet (linked to this strategy for FK)
        wallet = Wallet(
            id=str(uuid4()),
            strategy_id=strategy_id,
            initial_balance_usdt=initial_balance,
            available_usdt=initial_balance,
            peak_equity_usdt=initial_balance,
        )
        session.add(wallet)
        await flush_with_write_lock(session)
        return wallet

    # Per-strategy wallet mode (legacy)
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
        await flush_with_write_lock(session)
    return wallet


async def get_wallet(
    session: AsyncSession,
    strategy_id: str,
) -> Wallet | None:
    """Fetch the wallet for a strategy, respecting shared wallet mode."""
    settings = get_settings()
    if settings.shared_wallet_enabled:
        result = await session.execute(
            select(Wallet).order_by(Wallet.initial_balance_usdt.desc()).limit(1)
        )
        return result.scalar_one_or_none()
    result = await session.execute(
        select(Wallet).where(Wallet.strategy_id == strategy_id)
    )
    return result.scalar_one_or_none()


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
    await flush_with_write_lock(session)


async def credit_wallet(
    session: AsyncSession,
    wallet: Wallet,
    amount: Decimal,
) -> None:
    """Add amount to available USDT."""
    wallet.available_usdt = wallet.available_usdt + amount
    await flush_with_write_lock(session)


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
    await flush_with_write_lock(session)
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


async def get_positions(
    session: AsyncSession,
    strategy_id: str,
) -> list[Position]:
    result = await session.execute(
        select(Position).where(Position.strategy_id == strategy_id)
    )
    return list(result.scalars().all())


async def close_position(
    session: AsyncSession,
    position: Position,
) -> None:
    """Remove a position (fully closed)."""
    await session.delete(position)
    await flush_with_write_lock(session)
