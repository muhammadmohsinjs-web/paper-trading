"""Shared test fixtures."""

import pytest
import pytest_asyncio
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.models.strategy import Strategy
from app.market.data_store import Candle, DataStore


# Use asyncio mode for all async tests
def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite async session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_with_strategy(db_session):
    """DB session with a default test strategy inserted."""
    strategy = Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        config_json={},
    )
    db_session.add(strategy)
    await db_session.commit()
    return db_session, strategy


@pytest_asyncio.fixture
async def funded_wallet(db_session_with_strategy):
    """DB session with strategy and a funded wallet ($10,000)."""
    from app.engine.wallet_manager import get_or_create_wallet

    session, strategy = db_session_with_strategy
    wallet = await get_or_create_wallet(session, strategy.id, Decimal("10000"))
    return session, strategy, wallet


@pytest.fixture
def data_store():
    """Fresh DataStore instance, reset on teardown."""
    DataStore.reset()
    store = DataStore()
    yield store
    DataStore.reset()


@pytest.fixture
def make_candles():
    """Factory for generating candle lists with configurable patterns."""

    def _make(
        count: int = 200,
        base_price: float = 85000.0,
        trend: float = 0.0,
        volatility: float = 100.0,
        base_volume: float = 1000.0,
        start_time: int = 1700000000000,
        interval_ms: int = 300000,
    ) -> list[Candle]:
        candles = []
        for i in range(count):
            mid = base_price + trend * i
            candles.append(
                Candle(
                    open_time=start_time + i * interval_ms,
                    open=mid - volatility * 0.1,
                    high=mid + volatility,
                    low=mid - volatility,
                    close=mid + volatility * 0.1,
                    volume=base_volume + i * 10,
                )
            )
        return candles

    return _make
