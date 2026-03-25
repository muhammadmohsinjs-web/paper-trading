from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base  # noqa: F401

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def _ensure_phase3_strategy_columns() -> None:
    if engine.url.get_backend_name() != "sqlite":
        return

    column_defs = {
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

    async with engine.begin() as connection:
        result = await connection.execute(text("PRAGMA table_info(strategies)"))
        existing = {row[1] for row in result}
        for name, definition in column_defs.items():
            if name not in existing:
                await connection.execute(text(f"ALTER TABLE strategies ADD COLUMN {name} {definition}"))


async def _ensure_risk_management_columns() -> None:
    """Add risk-management columns for Phase 4 (backward-compatible)."""
    if engine.url.get_backend_name() != "sqlite":
        return

    async with engine.begin() as connection:
        # -- positions table --
        result = await connection.execute(text("PRAGMA table_info(positions)"))
        existing = {row[1] for row in result}
        if "stop_loss_price" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN stop_loss_price NUMERIC(24,12)"))
        if "take_profit_price" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN take_profit_price NUMERIC(24,12)"))
        if "trailing_stop_price" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN trailing_stop_price NUMERIC(24,12)"))
        if "entry_atr" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN entry_atr NUMERIC(24,12)"))
        if "entry_confidence_raw" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN entry_confidence_raw NUMERIC(8,4)"))
        if "entry_confidence_final" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN entry_confidence_final NUMERIC(8,4)"))
        if "entry_confidence_bucket" not in existing:
            await connection.execute(text("ALTER TABLE positions ADD COLUMN entry_confidence_bucket VARCHAR(16)"))

        # -- wallets table --
        result = await connection.execute(text("PRAGMA table_info(wallets)"))
        existing = {row[1] for row in result}
        if "peak_equity_usdt" not in existing:
            await connection.execute(text("ALTER TABLE wallets ADD COLUMN peak_equity_usdt NUMERIC(18,8) NOT NULL DEFAULT 1000"))
        wallet_cols = {
            "daily_loss_usdt": "NUMERIC(18,8) NOT NULL DEFAULT 0",
            "daily_loss_reset_date": "DATE",
            "weekly_loss_usdt": "NUMERIC(18,8) NOT NULL DEFAULT 0",
            "weekly_loss_reset_date": "DATE",
        }
        for name, definition in wallet_cols.items():
            if name not in existing:
                await connection.execute(text(f"ALTER TABLE wallets ADD COLUMN {name} {definition}"))

        # -- strategies table --
        strategy_cols = {
            "stop_loss_pct": "NUMERIC(6,3) NOT NULL DEFAULT 3.0",
            "max_drawdown_pct": "NUMERIC(6,3) NOT NULL DEFAULT 15.0",
            "risk_per_trade_pct": "NUMERIC(6,3) NOT NULL DEFAULT 2.0",
            "max_position_size_pct": "NUMERIC(6,3) NOT NULL DEFAULT 30.0",
            "candle_interval": "VARCHAR(8) NOT NULL DEFAULT '1h'",
            "consecutive_losses": "INTEGER NOT NULL DEFAULT 0",
            "max_consecutive_losses": "INTEGER NOT NULL DEFAULT 0",
            "streak_size_multiplier": "NUMERIC(6,3) NOT NULL DEFAULT 1.0",
        }
        result = await connection.execute(text("PRAGMA table_info(strategies)"))
        existing = {row[1] for row in result}
        for name, definition in strategy_cols.items():
            if name not in existing:
                await connection.execute(text(f"ALTER TABLE strategies ADD COLUMN {name} {definition}"))


async def _ensure_trade_log_columns() -> None:
    """Add trade log context columns (backward-compatible)."""
    if engine.url.get_backend_name() != "sqlite":
        return

    column_defs = {
        "strategy_name": "VARCHAR(128)",
        "strategy_type": "VARCHAR(64)",
        "decision_source": "VARCHAR(32)",
        "indicator_snapshot": "TEXT",  # JSON stored as TEXT in SQLite
        "composite_score": "NUMERIC(8,4)",
        "composite_confidence": "NUMERIC(8,4)",
        "entry_confidence_raw": "NUMERIC(8,4)",
        "entry_confidence_final": "NUMERIC(8,4)",
        "entry_confidence_bucket": "VARCHAR(16)",
        "cost_usdt": "NUMERIC(18,8)",
        "wallet_balance_before": "NUMERIC(18,8)",
        "wallet_balance_after": "NUMERIC(18,8)",
    }

    async with engine.begin() as connection:
        result = await connection.execute(text("PRAGMA table_info(trades)"))
        existing = {row[1] for row in result}
        for name, definition in column_defs.items():
            if name not in existing:
                await connection.execute(text(f"ALTER TABLE trades ADD COLUMN {name} {definition}"))


async def _backfill_trade_log_columns() -> None:
    """Backfill cost_usdt, strategy_name, strategy_type for existing trades."""
    if engine.url.get_backend_name() != "sqlite":
        return

    async with engine.begin() as connection:
        # Backfill cost_usdt = quantity * price for trades missing it
        await connection.execute(text(
            "UPDATE trades SET cost_usdt = quantity * price WHERE cost_usdt IS NULL"
        ))
        # Backfill strategy_name and strategy_type from strategies table
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


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _ensure_phase3_strategy_columns()
    await _ensure_risk_management_columns()
    await _ensure_trade_log_columns()
    await _backfill_trade_log_columns()


async def dispose_database() -> None:
    await engine.dispose()
