"""Tests for cross-process strategy cycle locking."""

import asyncio
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.engine import trading_loop
from app.strategies.manager import StrategyManager


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


@pytest.mark.asyncio
async def test_strategy_loop_does_not_call_run_single_cycle_while_lock_is_held(monkeypatch):
    StrategyManager.reset()

    calls: list[str] = []

    async def fake_run_single_cycle(
        strategy_id: str,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        force: bool = False,
    ):
        del symbol, interval, force
        lock = StrategyManager.get_instance().get_lock(strategy_id)
        assert not lock.locked()
        calls.append(strategy_id)
        return {"status": "skipped", "reason": "test"}

    async def stop_after_first_sleep(_: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(trading_loop, "run_single_cycle", fake_run_single_cycle)
    monkeypatch.setattr(trading_loop.asyncio, "sleep", stop_after_first_sleep)

    with pytest.raises(asyncio.CancelledError):
        await trading_loop.strategy_loop("strategy-1", interval_seconds=60)

    assert calls == ["strategy-1"]
