import asyncio

import pytest

from app import main
from app.strategies.manager import StrategyManager


@pytest.mark.asyncio
async def test_stop_ws_clients_runs_concurrently() -> None:
    stopped: list[str] = []
    release = asyncio.Event()

    class FakeClient:
        def __init__(self, name: str) -> None:
            self.name = name

        async def stop(self) -> None:
            stopped.append(self.name)
            if len(stopped) == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=0.1)

    clients = [FakeClient("btc"), FakeClient("eth")]

    await asyncio.wait_for(main._stop_ws_clients(clients), timeout=0.2)

    assert set(stopped) == {"btc", "eth"}


@pytest.mark.asyncio
async def test_strategy_manager_stop_all_cancels_tasks_before_awaiting() -> None:
    manager = StrategyManager()
    cancelled: list[str] = []
    release = asyncio.Event()

    async def worker(name: str) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(name)
            if len(cancelled) == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=0.1)
            raise

    task_a = asyncio.create_task(worker("strategy-a"))
    task_b = asyncio.create_task(worker("strategy-b"))
    await asyncio.sleep(0)

    manager._tasks = {
        "strategy-a": task_a,
        "strategy-b": task_b,
    }

    stopped = await asyncio.wait_for(manager.stop_all(), timeout=0.2)

    assert stopped == 2
    assert set(cancelled) == {"strategy-a", "strategy-b"}
