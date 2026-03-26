from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base  # noqa: F401

settings = get_settings()
logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if engine.url.get_backend_name() != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA busy_timeout=5000")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass  # WAL switch may fail if another process holds the DB; non-fatal
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def _run_migrations(connection) -> None:
    """Run all backward-compatible migrations in a single connection/transaction."""

    # ── strategies table ──────────────────────────────────────────────
    result = await connection.execute(text("PRAGMA table_info(strategies)"))
    existing_strategy_cols = {row[1] for row in result}

    ai_columns = {
        "ai_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "ai_provider": "VARCHAR(32) NOT NULL DEFAULT 'anthropic'",
        "ai_strategy_key": "VARCHAR(64)",
        "ai_model": "VARCHAR(128)",
        "ai_cooldown_seconds": "INTEGER NOT NULL DEFAULT 60",
        "ai_max_tokens": "INTEGER NOT NULL DEFAULT 700",
        "ai_temperature": "NUMERIC(6, 3) NOT NULL DEFAULT 0.2",
        "ai_last_decision_at": "DATETIME",
        "ai_last_decision_status": "VARCHAR(32)",
        "ai_last_reasoning": "TEXT",
        "ai_last_provider": "VARCHAR(32)",
        "ai_last_model": "VARCHAR(128)",
        "ai_last_prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
        "ai_last_completion_tokens": "INTEGER NOT NULL DEFAULT 0",
        "ai_last_total_tokens": "INTEGER NOT NULL DEFAULT 0",
        "ai_last_cost_usdt": "NUMERIC(18, 8) NOT NULL DEFAULT 0",
        "ai_total_calls": "INTEGER NOT NULL DEFAULT 0",
        "ai_total_prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
        "ai_total_completion_tokens": "INTEGER NOT NULL DEFAULT 0",
        "ai_total_tokens": "INTEGER NOT NULL DEFAULT 0",
        "ai_total_cost_usdt": "NUMERIC(18, 8) NOT NULL DEFAULT 0",
    }
    risk_strategy_columns = {
        "stop_loss_pct": "NUMERIC(6,3) NOT NULL DEFAULT 3.0",
        "max_drawdown_pct": "NUMERIC(6,3) NOT NULL DEFAULT 15.0",
        "risk_per_trade_pct": "NUMERIC(6,3) NOT NULL DEFAULT 2.0",
        "max_position_size_pct": "NUMERIC(6,3) NOT NULL DEFAULT 30.0",
        "candle_interval": "VARCHAR(8) NOT NULL DEFAULT '1h'",
        "consecutive_losses": "INTEGER NOT NULL DEFAULT 0",
        "max_consecutive_losses": "INTEGER NOT NULL DEFAULT 0",
        "streak_size_multiplier": "NUMERIC(6,3) NOT NULL DEFAULT 1.0",
    }
    multicoin_columns = {
        "execution_mode": "VARCHAR(32) NOT NULL DEFAULT 'single_symbol'",
        "primary_symbol": "VARCHAR(24) NOT NULL DEFAULT 'BTCUSDT'",
        "scan_universe_json": "JSON NOT NULL DEFAULT '[]'",
        "top_pick_count": "INTEGER NOT NULL DEFAULT 5",
        "selection_hour_utc": "INTEGER NOT NULL DEFAULT 0",
        "max_concurrent_positions": "INTEGER NOT NULL DEFAULT 2",
    }
    for col_map in (ai_columns, risk_strategy_columns, multicoin_columns):
        for name, definition in col_map.items():
            if name not in existing_strategy_cols:
                await connection.execute(text(f"ALTER TABLE strategies ADD COLUMN {name} {definition}"))

    # ── positions table ───────────────────────────────────────────────
    result = await connection.execute(text("PRAGMA table_info(positions)"))
    existing_pos_cols = {row[1] for row in result}
    position_columns = {
        "stop_loss_price": "NUMERIC(24,12)",
        "take_profit_price": "NUMERIC(24,12)",
        "trailing_stop_price": "NUMERIC(24,12)",
        "entry_atr": "NUMERIC(24,12)",
        "entry_confidence_raw": "NUMERIC(8,4)",
        "entry_confidence_final": "NUMERIC(8,4)",
        "entry_confidence_bucket": "VARCHAR(16)",
        "take_profit_1_price": "NUMERIC(24,12)",
        "take_profit_2_price": "NUMERIC(24,12)",
        "take_profit_3_price": "NUMERIC(24,12)",
        "tp1_hit": "BOOLEAN DEFAULT 0",
        "tp2_hit": "BOOLEAN DEFAULT 0",
    }
    for name, definition in position_columns.items():
        if name not in existing_pos_cols:
            await connection.execute(text(f"ALTER TABLE positions ADD COLUMN {name} {definition}"))

    # ── wallets table ─────────────────────────────────────────────────
    result = await connection.execute(text("PRAGMA table_info(wallets)"))
    existing_wallet_cols = {row[1] for row in result}
    wallet_columns = {
        "peak_equity_usdt": "NUMERIC(18,8) NOT NULL DEFAULT 1000",
        "daily_loss_usdt": "NUMERIC(18,8) NOT NULL DEFAULT 0",
        "daily_loss_reset_date": "DATE",
        "weekly_loss_usdt": "NUMERIC(18,8) NOT NULL DEFAULT 0",
        "weekly_loss_reset_date": "DATE",
    }
    for name, definition in wallet_columns.items():
        if name not in existing_wallet_cols:
            await connection.execute(text(f"ALTER TABLE wallets ADD COLUMN {name} {definition}"))

    # ── trades table ──────────────────────────────────────────────────
    result = await connection.execute(text("PRAGMA table_info(trades)"))
    existing_trade_cols = {row[1] for row in result}
    trade_columns = {
        "strategy_name": "VARCHAR(128)",
        "strategy_type": "VARCHAR(64)",
        "decision_source": "VARCHAR(32)",
        "indicator_snapshot": "TEXT",
        "composite_score": "NUMERIC(8,4)",
        "composite_confidence": "NUMERIC(8,4)",
        "entry_confidence_raw": "NUMERIC(8,4)",
        "entry_confidence_final": "NUMERIC(8,4)",
        "entry_confidence_bucket": "VARCHAR(16)",
        "cost_usdt": "NUMERIC(18,8)",
        "wallet_balance_before": "NUMERIC(18,8)",
        "wallet_balance_after": "NUMERIC(18,8)",
    }
    for name, definition in trade_columns.items():
        if name not in existing_trade_cols:
            await connection.execute(text(f"ALTER TABLE trades ADD COLUMN {name} {definition}"))

    # ── Backfill trades ───────────────────────────────────────────────
    await connection.execute(text(
        "UPDATE trades SET cost_usdt = quantity * price WHERE cost_usdt IS NULL"
    ))
    await connection.execute(text(
        "UPDATE trades SET strategy_name = ("
        "  SELECT s.name FROM strategies s WHERE s.id = trades.strategy_id"
        ") WHERE strategy_name IS NULL"
    ))
    await connection.execute(text(
        "UPDATE trades SET strategy_type = ("
        "  SELECT json_extract(s.config_json, '$.strategy_type') FROM strategies s WHERE s.id = trades.strategy_id"
        ") WHERE strategy_type IS NULL"
    ))

    # ── Cleanup orphan rows ───────────────────────────────────────────
    orphan_tables = (
        "wallets", "positions", "trades", "snapshots",
        "daily_picks", "ai_call_logs", "strategy_cycle_locks",
    )
    for table_name in orphan_tables:
        result = await connection.execute(text(f"PRAGMA table_info({table_name})"))
        columns = {row[1] for row in result}
        if "strategy_id" not in columns:
            continue
        await connection.execute(text(
            f"DELETE FROM {table_name} "
            "WHERE strategy_id IS NOT NULL "
            "AND strategy_id NOT IN (SELECT id FROM strategies)"
        ))


async def init_database() -> None:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if engine.url.get_backend_name() == "sqlite":
                await _run_migrations(connection)
    except OperationalError:
        if engine.url.get_backend_name() == "sqlite":
            logger.exception(
                "database initialization failed because the sqlite file is locked db=%s; "
                "close other writers such as DB Browser, pytest, or another server process",
                engine.url.database,
            )
        raise


async def dispose_database() -> None:
    await engine.dispose()
