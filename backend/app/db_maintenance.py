from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.ai_call_log import AICallLog
from app.models.position import Position
from app.models.price_cache import PriceCache
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.wallet import Wallet

RUNTIME_TABLES = (
    "ai_call_logs",
    "positions",
    "price_cache",
    "snapshots",
    "strategy_cycle_locks",
    "trades",
    "wallets",
)


async def _existing_tables(session: AsyncSession) -> set[str]:
    return set(await session.run_sync(lambda sync_session: inspect(sync_session.bind).get_table_names()))


async def _count_rows(session: AsyncSession, table_name: str) -> int:
    result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return int(result.scalar_one())


def _strategy_initial_balance(strategy: Strategy, default_balance: float) -> Decimal:
    config = strategy.config_json or {}
    return Decimal(str(config.get("initial_balance", default_balance)))


def _reset_strategy_runtime_fields(strategy: Strategy) -> None:
    strategy.ai_last_decision_at = None
    strategy.ai_last_decision_status = None
    strategy.ai_last_reasoning = None
    strategy.ai_last_provider = None
    strategy.ai_last_model = None
    strategy.ai_last_prompt_tokens = 0
    strategy.ai_last_completion_tokens = 0
    strategy.ai_last_total_tokens = 0
    strategy.ai_last_cost_usdt = Decimal("0")
    strategy.ai_total_calls = 0
    strategy.ai_total_prompt_tokens = 0
    strategy.ai_total_completion_tokens = 0
    strategy.ai_total_tokens = 0
    strategy.ai_total_cost_usdt = Decimal("0")
    strategy.consecutive_losses = 0
    strategy.max_consecutive_losses = 0
    strategy.streak_size_multiplier = Decimal("1.0")


async def reset_runtime_data(session: AsyncSession) -> dict[str, int]:
    settings = get_settings()
    existing_tables = await _existing_tables(session)

    summary: dict[str, int] = {}
    for table_name in RUNTIME_TABLES:
        if table_name in existing_tables:
            summary[table_name] = await _count_rows(session, table_name)

    strategies = list((await session.execute(select(Strategy).order_by(Strategy.created_at.asc()))).scalars())
    summary["strategies"] = len(strategies)

    if "ai_call_logs" in existing_tables:
        await session.execute(delete(AICallLog))
    if "positions" in existing_tables:
        await session.execute(delete(Position))
    if "price_cache" in existing_tables:
        await session.execute(delete(PriceCache))
    if "snapshots" in existing_tables:
        await session.execute(delete(Snapshot))
    if "strategy_cycle_locks" in existing_tables:
        await session.execute(text("DELETE FROM strategy_cycle_locks"))
    if "trades" in existing_tables:
        await session.execute(delete(Trade))
    if "wallets" in existing_tables:
        await session.execute(delete(Wallet))

    now = datetime.now(timezone.utc)
    week_start = now.date() - timedelta(days=now.weekday())
    wallets_recreated = 0

    for strategy in strategies:
        _reset_strategy_runtime_fields(strategy)
        initial_balance = _strategy_initial_balance(strategy, settings.default_balance_usdt)
        session.add(
            Wallet(
                id=str(uuid4()),
                strategy_id=strategy.id,
                initial_balance_usdt=initial_balance,
                available_usdt=initial_balance,
                peak_equity_usdt=initial_balance,
                daily_loss_usdt=Decimal("0"),
                daily_loss_reset_date=now.date(),
                weekly_loss_usdt=Decimal("0"),
                weekly_loss_reset_date=week_start,
            )
        )
        wallets_recreated += 1

    await session.flush()
    summary["wallets_recreated"] = wallets_recreated
    return summary
