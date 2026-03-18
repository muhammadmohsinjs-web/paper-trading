"""Strategy manager — spawns and manages parallel asyncio tasks."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.database import SessionLocal
from app.engine.trading_loop import strategy_loop
from app.models.strategy import Strategy

logger = logging.getLogger(__name__)


class StrategyManager:
    """Manages one asyncio.Task per active strategy."""

    _instance: StrategyManager | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    @classmethod
    def get_instance(cls) -> StrategyManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    async def start_strategy(self, strategy_id: str, interval_seconds: int = 300) -> bool:
        if strategy_id in self._tasks and not self._tasks[strategy_id].done():
            logger.info("Strategy %s already running", strategy_id)
            return False

        task = asyncio.create_task(
            strategy_loop(strategy_id, interval_seconds),
            name=f"strategy-{strategy_id}",
        )
        self._tasks[strategy_id] = task
        logger.info("Started strategy %s", strategy_id)
        return True

    async def stop_strategy(self, strategy_id: str) -> bool:
        task = self._tasks.pop(strategy_id, None)
        if task is None:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped strategy %s", strategy_id)
        return True

    async def start_all_active(self) -> int:
        """Start tasks for all strategies marked as active in DB."""
        count = 0
        async with SessionLocal() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active == True)  # noqa: E712
            )
            strategies = result.scalars().all()
            for s in strategies:
                interval = (s.config_json or {}).get("interval_seconds", 300)
                started = await self.start_strategy(s.id, interval)
                if started:
                    count += 1
        return count

    async def stop_all(self) -> int:
        count = 0
        for sid in list(self._tasks.keys()):
            await self.stop_strategy(sid)
            count += 1
        return count

    def running_strategies(self) -> list[str]:
        return [sid for sid, t in self._tasks.items() if not t.done()]
