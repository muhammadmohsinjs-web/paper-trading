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
        "ai_strategy_key": "VARCHAR(64)",
        "ai_model": "VARCHAR(128)",
        "ai_cooldown_seconds": "INTEGER NOT NULL DEFAULT 60",
        "ai_max_tokens": "INTEGER NOT NULL DEFAULT 700",
        "ai_temperature": "NUMERIC(6, 3) NOT NULL DEFAULT 0.2",
        "ai_last_decision_at": "DATETIME",
        "ai_last_decision_status": "VARCHAR(32)",
        "ai_last_reasoning": "TEXT",
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


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _ensure_phase3_strategy_columns()


async def dispose_database() -> None:
    await engine.dispose()
