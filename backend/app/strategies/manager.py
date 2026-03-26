"""Strategy manager — spawns and manages parallel asyncio tasks."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.database import SessionLocal
from app.engine.trading_loop import INTERVAL_TO_SECONDS, strategy_loop
from app.models.strategy import Strategy

logger = logging.getLogger(__name__)


def resolve_strategy_interval(strategy: Strategy) -> int:
    """Resolve runtime loop interval, never faster than the configured candle cadence."""
    candle_seconds = INTERVAL_TO_SECONDS.get(strategy.candle_interval or "1h", 3600)
    config_interval = ((strategy.config_json or {}).get("interval_seconds", candle_seconds))
    return max(int(config_interval), candle_seconds)


class StrategyManager:
    """Manages one asyncio.Task per active strategy."""

    _instance: StrategyManager | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, strategy_id: str) -> asyncio.Lock:
        """Return (creating if needed) a per-strategy lock to prevent concurrent cycles."""
        if strategy_id not in self._locks:
            self._locks[strategy_id] = asyncio.Lock()
        return self._locks[strategy_id]

    @classmethod
    def get_instance(cls) -> StrategyManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    async def start_strategy(self, strategy_id: str, interval_seconds: int = 3600) -> bool:
        if strategy_id in self._tasks and not self._tasks[strategy_id].done():
            logger.info("strategy already running strategy_id=%s", strategy_id)
            return False

        task = asyncio.create_task(
            strategy_loop(strategy_id, interval_seconds),
            name=f"strategy-{strategy_id}",
        )
        self._tasks[strategy_id] = task
        logger.info(
            "strategy started strategy_id=%s interval_seconds=%d",
            strategy_id,
            interval_seconds,
        )
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
        logger.info("strategy stopped strategy_id=%s", strategy_id)
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
                interval = resolve_strategy_interval(s)
                started = await self.start_strategy(s.id, interval)
                if started:
                    count += 1
        return count

    async def stop_all(self) -> int:
        active_tasks = [(sid, task) for sid, task in list(self._tasks.items()) if task is not None]
        if not active_tasks:
            return 0

        self._tasks.clear()
        for _, task in active_tasks:
            task.cancel()

        results = await asyncio.gather(
            *(task for _, task in active_tasks),
            return_exceptions=True,
        )
        for (sid, _), result in zip(active_tasks, results):
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                logger.error(
                    "strategy stop failed strategy_id=%s",
                    sid,
                    exc_info=(type(result), result, result.__traceback__),
                )
            logger.info("strategy stopped strategy_id=%s", sid)

        return len(active_tasks)

    def running_strategies(self) -> list[str]:
        return [sid for sid, t in self._tasks.items() if not t.done()]
