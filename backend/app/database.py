from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base  # noqa: F401

settings = get_settings()
logger = logging.getLogger(__name__)
_sqlite_write_lock: asyncio.Lock | None = None
_sqlite_write_lock_loop: asyncio.AbstractEventLoop | None = None
_SQLITE_WRITE_LOCK_HELD_KEY = "_sqlite_write_lock_held"
_SQLITE_WRITE_PREFIXES = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "INSERT",
    "PRAGMA",
    "REINDEX",
    "REPLACE",
    "UPDATE",
    "VACUUM",
}


def _sqlite_enabled() -> bool:
    return engine.url.get_backend_name() == "sqlite"


def _get_sqlite_write_lock() -> asyncio.Lock:
    global _sqlite_write_lock, _sqlite_write_lock_loop

    loop = asyncio.get_running_loop()
    if _sqlite_write_lock is None or _sqlite_write_lock_loop is not loop:
        _sqlite_write_lock = asyncio.Lock()
        _sqlite_write_lock_loop = loop

    return _sqlite_write_lock


def _statement_needs_write_lock(statement: Any) -> bool:
    if getattr(statement, "is_insert", False):
        return True
    if getattr(statement, "is_update", False):
        return True
    if getattr(statement, "is_delete", False):
        return True

    text_value = getattr(statement, "text", None)
    if not isinstance(text_value, str):
        return False

    match = re.match(r"^\s*([A-Za-z]+)", text_value)
    if match is None:
        return False

    prefix = match.group(1).upper()
    if prefix != "PRAGMA":
        return prefix in _SQLITE_WRITE_PREFIXES

    return "=" in text_value


async def _acquire_sqlite_write_lease(session: AsyncSession) -> None:
    if not _sqlite_enabled():
        return
    if session.info.get(_SQLITE_WRITE_LOCK_HELD_KEY):
        return

    await _get_sqlite_write_lock().acquire()
    session.info[_SQLITE_WRITE_LOCK_HELD_KEY] = True


async def _release_sqlite_write_lease(session: AsyncSession) -> None:
    if not _sqlite_enabled():
        return
    if not session.info.pop(_SQLITE_WRITE_LOCK_HELD_KEY, False):
        return

    _get_sqlite_write_lock().release()


class SQLiteLockedAsyncSession(AsyncSession):
    async def execute(self, statement: Any, params: Any = None, /, **kwargs: Any):
        if _statement_needs_write_lock(statement):
            await _acquire_sqlite_write_lease(self)
        return await super().execute(statement, params, **kwargs)

    async def flush(self, objects: Any = None) -> None:
        if self.new or self.dirty or self.deleted:
            await _acquire_sqlite_write_lease(self)
        await super().flush(objects=objects)

    async def commit(self) -> None:
        await _acquire_sqlite_write_lease(self)
        try:
            await super().commit()
        finally:
            await _release_sqlite_write_lease(self)

    async def rollback(self) -> None:
        try:
            await super().rollback()
        finally:
            await _release_sqlite_write_lease(self)

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            await _release_sqlite_write_lease(self)

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
    cursor.execute("PRAGMA busy_timeout=30000")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass  # WAL switch may fail if another process holds the DB; non-fatal
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=SQLiteLockedAsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


@asynccontextmanager
async def sqlite_write_guard() -> AsyncIterator[None]:
    """Serialize SQLite writes within this process to avoid lock contention."""
    if not _sqlite_enabled():
        yield
        return

    async with _get_sqlite_write_lock():
        yield


async def execute_with_write_lock(
    session: AsyncSession,
    statement: Any,
    params: dict[str, Any] | None = None,
):
    await _acquire_sqlite_write_lease(session)
    if params is None:
        return await session.execute(statement)
    return await session.execute(statement, params)


async def flush_with_write_lock(session: AsyncSession) -> None:
    await _acquire_sqlite_write_lease(session)
    await session.flush()


async def commit_with_write_lock(session: AsyncSession) -> None:
    await _acquire_sqlite_write_lease(session)
    try:
        await session.commit()
    finally:
        await _release_sqlite_write_lease(session)


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
    cooldown_columns = {
        "last_stop_loss_symbol": "VARCHAR(24)",
        "last_stop_loss_at": "DATETIME",
    }
    for col_map in (ai_columns, risk_strategy_columns, multicoin_columns, cooldown_columns):
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
        "daily_picks", "ai_call_logs", "symbol_evaluation_logs", "strategy_cycle_locks", "symbol_ownership",
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

    await connection.execute(text(
        """
        CREATE TABLE IF NOT EXISTS symbol_evaluation_logs (
            id VARCHAR(36) PRIMARY KEY,
            strategy_id VARCHAR(36) NOT NULL,
            cycle_id VARCHAR(36) NOT NULL,
            symbol VARCHAR(24) NOT NULL,
            stage VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            reason_code VARCHAR(64),
            reason_text TEXT,
            metrics_json JSON NOT NULL DEFAULT '{}',
            context_json JSON NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
        )
        """
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_evaluation_logs_strategy_id "
        "ON symbol_evaluation_logs(strategy_id)"
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_evaluation_logs_cycle_id "
        "ON symbol_evaluation_logs(cycle_id)"
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_evaluation_logs_symbol "
        "ON symbol_evaluation_logs(symbol)"
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_evaluation_logs_stage "
        "ON symbol_evaluation_logs(stage)"
    ))

    await connection.execute(text(
        """
        CREATE TABLE IF NOT EXISTS symbol_ownership (
            id VARCHAR(36) PRIMARY KEY,
            symbol VARCHAR(24) NOT NULL,
            strategy_id VARCHAR(36) NOT NULL,
            strategy_name VARCHAR(120) NOT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            released_at DATETIME,
            release_reason VARCHAR(64),
            cooldown_until DATETIME,
            assignment_score FLOAT,
            assignment_reason TEXT,
            FOREIGN KEY(strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
        )
        """
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_ownership_symbol "
        "ON symbol_ownership(symbol)"
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_ownership_strategy_id "
        "ON symbol_ownership(strategy_id)"
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_ownership_released_at "
        "ON symbol_ownership(released_at)"
    ))
    await connection.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_symbol_ownership_cooldown_until "
        "ON symbol_ownership(cooldown_until)"
    ))

    result = await connection.execute(text("PRAGMA table_info(daily_picks)"))
    existing_daily_pick_cols = {row[1] for row in result}
    daily_pick_columns = {
        "assignment_reason": "TEXT",
        "conflict_resolution": "VARCHAR(32)",
        "setup_fit_score": "FLOAT",
        "regime_fit_score": "FLOAT",
    }
    for name, definition in daily_pick_columns.items():
        if name not in existing_daily_pick_cols:
            await connection.execute(text(f"ALTER TABLE daily_picks ADD COLUMN {name} {definition}"))


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
