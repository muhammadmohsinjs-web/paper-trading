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
