"""Tests for order executor and wallet manager."""

import pytest
import pytest_asyncio
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.models.strategy import Strategy
from app.engine.executor import execute_buy, execute_sell
from app.engine.wallet_manager import get_or_create_wallet, get_position


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # Create a test strategy
        strategy = Strategy(
            id="test-strategy-1",
            name="Test Strategy",
            config_json={},
        )
        session.add(strategy)
        await session.commit()
        yield session

    await engine.dispose()


# Keep local fixture for backward compat — existing tests use "test-strategy-1"


@pytest.mark.asyncio
async def test_buy_debits_wallet(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))
    result = await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("1.0"),
    )
    assert result.success
    assert wallet.available_usdt < Decimal("1000")
    assert result.trade.side.value == "BUY"
    assert result.trade.fee > 0


@pytest.mark.asyncio
async def test_buy_creates_position(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))
    await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("0.5"),
    )
    position = await get_position(db_session, "test-strategy-1", "BTCUSDT")
    assert position is not None
    assert position.quantity > 0


@pytest.mark.asyncio
async def test_sell_credits_wallet_and_closes_position(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))

    # Buy first
    await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("1.0"),
    )
    balance_after_buy = wallet.available_usdt

    # Sell all
    result = await execute_sell(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("1.0"),
    )
    assert result.success
    assert result.trade.side.value == "SELL"
    assert result.trade.pnl is not None
    assert wallet.available_usdt > balance_after_buy

    # Position should be closed
    position = await get_position(db_session, "test-strategy-1", "BTCUSDT")
    assert position is None


@pytest.mark.asyncio
async def test_sell_without_position_fails(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))
    result = await execute_sell(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"),
    )
    assert not result.success
    assert "No position" in result.error


@pytest.mark.asyncio
async def test_round_trip_loses_fees(db_session: AsyncSession):
    """Buy then sell at same price should result in net loss (fees + slippage)."""
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))
    price = Decimal("50000")

    await execute_buy(db_session, "test-strategy-1", wallet, "BTCUSDT", price, Decimal("1.0"))
    await execute_sell(db_session, "test-strategy-1", wallet, "BTCUSDT", price, Decimal("1.0"))

    # Should have less than initial due to fees + slippage
    assert wallet.available_usdt < Decimal("1000")


@pytest.mark.asyncio
async def test_partial_sell_leaves_remaining_position(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))
    await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("1.0"),
    )
    position_before = await get_position(db_session, "test-strategy-1", "BTCUSDT")
    qty_before = position_before.quantity

    result = await execute_sell(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("0.5"),
    )
    assert result.success

    position_after = await get_position(db_session, "test-strategy-1", "BTCUSDT")
    assert position_after is not None
    assert position_after.quantity < qty_before
    assert position_after.quantity > Decimal("0")


@pytest.mark.asyncio
async def test_position_averaging_two_buys(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("10000"))

    await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("0.25"),
    )
    pos1 = await get_position(db_session, "test-strategy-1", "BTCUSDT")
    entry1 = pos1.entry_price
    qty1 = pos1.quantity

    await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("60000"), Decimal("0.25"),
    )
    pos2 = await get_position(db_session, "test-strategy-1", "BTCUSDT")

    # Entry price should be between the two prices (weighted average)
    assert pos2.entry_price > Decimal("50000")
    assert pos2.entry_price < Decimal("60000")
    assert pos2.quantity > qty1


@pytest.mark.asyncio
async def test_buy_zero_balance_fails(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("0"))
    result = await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("1.0"),
    )
    assert not result.success
    assert "Nothing to spend" in result.error


@pytest.mark.asyncio
async def test_buy_quantity_pct_partial(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-strategy-1", Decimal("1000"))
    initial = wallet.available_usdt

    await execute_buy(
        db_session, "test-strategy-1", wallet, "BTCUSDT",
        Decimal("50000"), Decimal("0.5"),
    )
    # Should have spent approximately 50% of balance (minus fees/slippage)
    spent = initial - wallet.available_usdt
    assert spent > Decimal("490")
    assert spent < Decimal("510")
