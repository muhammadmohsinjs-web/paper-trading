"""Tests for cross-process strategy cycle locking."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.engine import trading_loop


@pytest.mark.asyncio
async def test_cycle_db_lock_allows_single_owner(tmp_path, monkeypatch):
    db_path = tmp_path / "cycle-locks.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(trading_loop, "SessionLocal", session_factory)
    monkeypatch.setattr(trading_loop, "_cycle_lock_table_ready", False)

    owner_1 = await trading_loop._acquire_cycle_db_lock("strategy-1")
    owner_2 = await trading_loop._acquire_cycle_db_lock("strategy-1")

    assert owner_1 is not None
    assert owner_2 is None

    await trading_loop._release_cycle_db_lock("strategy-1", owner_1)
    owner_3 = await trading_loop._acquire_cycle_db_lock("strategy-1")

    assert owner_3 is not None
    assert owner_3 != owner_1

    await trading_loop._release_cycle_db_lock("strategy-1", owner_3)
    await engine.dispose()
