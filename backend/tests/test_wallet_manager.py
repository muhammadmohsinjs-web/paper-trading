"""Tests for wallet manager operations."""

import pytest
import pytest_asyncio
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.models.strategy import Strategy
from app.engine.wallet_manager import (
    credit_wallet,
    debit_wallet,
    get_or_create_wallet,
    get_position,
    open_position,
    close_position,
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        strategy = Strategy(id="test-1", name="Test", config_json={})
        session.add(strategy)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_create_wallet(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-1", Decimal("5000"))
    assert wallet.available_usdt == Decimal("5000")

    # Second call returns same wallet
    wallet2 = await get_or_create_wallet(db_session, "test-1")
    assert wallet2.id == wallet.id


@pytest.mark.asyncio
async def test_debit_wallet(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-1", Decimal("1000"))
    await debit_wallet(db_session, wallet, Decimal("300"))
    assert wallet.available_usdt == Decimal("700")


@pytest.mark.asyncio
async def test_debit_wallet_insufficient(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-1", Decimal("100"))
    with pytest.raises(ValueError, match="Insufficient"):
        await debit_wallet(db_session, wallet, Decimal("200"))


@pytest.mark.asyncio
async def test_credit_wallet(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-1", Decimal("500"))
    await credit_wallet(db_session, wallet, Decimal("200"))
    assert wallet.available_usdt == Decimal("700")


@pytest.mark.asyncio
async def test_open_and_close_position(db_session: AsyncSession):
    position = await open_position(
        db_session, "test-1", "BTCUSDT",
        Decimal("0.01"), Decimal("50000"), Decimal("0.5"),
    )
    assert position.quantity == Decimal("0.01")

    found = await get_position(db_session, "test-1", "BTCUSDT")
    assert found is not None
    assert found.id == position.id

    await close_position(db_session, position)
    assert await get_position(db_session, "test-1", "BTCUSDT") is None


@pytest.mark.asyncio
async def test_equity_equals_cash_plus_position(db_session: AsyncSession):
    """Equity = available USDT + position_qty * market_price."""
    from app.engine.post_trade import compute_equity as _compute_equity
    from types import SimpleNamespace

    wallet = await get_or_create_wallet(db_session, "test-1", Decimal("5000"))
    position = await open_position(
        db_session, "test-1", "BTCUSDT",
        Decimal("0.1"), Decimal("50000"), Decimal("5"),
    )
    equity = _compute_equity(wallet, position, Decimal("60000"))
    # 5000 + 0.1 * 60000 = 11000
    assert equity == Decimal("5000") + Decimal("0.1") * Decimal("60000")


@pytest.mark.asyncio
async def test_multi_strategy_wallet_isolation(db_session: AsyncSession):
    """Each strategy has its own independent wallet."""
    # Create second strategy
    strategy2 = Strategy(id="test-2", name="Test 2", config_json={})
    db_session.add(strategy2)
    await db_session.commit()

    wallet1 = await get_or_create_wallet(db_session, "test-1", Decimal("1000"))
    wallet2 = await get_or_create_wallet(db_session, "test-2", Decimal("2000"))

    assert wallet1.available_usdt == Decimal("1000")
    assert wallet2.available_usdt == Decimal("2000")

    await debit_wallet(db_session, wallet1, Decimal("500"))
    assert wallet1.available_usdt == Decimal("500")
    assert wallet2.available_usdt == Decimal("2000")  # Unchanged


@pytest.mark.asyncio
async def test_peak_equity_tracked(db_session: AsyncSession):
    wallet = await get_or_create_wallet(db_session, "test-1", Decimal("1000"))
    assert wallet.peak_equity_usdt == Decimal("1000")

    # Simulate profit: credit increases balance
    await credit_wallet(db_session, wallet, Decimal("500"))
    # Manually update peak like trading loop does
    if wallet.available_usdt > wallet.peak_equity_usdt:
        wallet.peak_equity_usdt = wallet.available_usdt
    assert wallet.peak_equity_usdt == Decimal("1500")
