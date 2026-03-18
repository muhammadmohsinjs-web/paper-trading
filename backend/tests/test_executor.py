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
