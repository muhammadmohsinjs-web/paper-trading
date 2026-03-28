"""Tests for strategy cycle locking."""

import asyncio
from typing import Optional

import pytest

from app.engine import trading_loop
from app.strategies.manager import StrategyManager


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
