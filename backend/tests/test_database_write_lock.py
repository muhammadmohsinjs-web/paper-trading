import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import SQLiteLockedAsyncSession


@pytest.mark.asyncio
async def test_sqlite_write_lease_waits_for_commit(tmp_path):
    db_path = tmp_path / "write-lease.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(
        engine,
        class_=SQLiteLockedAsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE test_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    value TEXT NOT NULL
                )
                """
            )
        )

    writer_started = asyncio.Event()
    writer_finished = asyncio.Event()

    async with session_factory() as session_1:
        await session_1.execute(
            text("INSERT INTO test_rows (value) VALUES ('first')")
        )

        async def writer_2() -> None:
            async with session_factory() as session_2:
                writer_started.set()
                await session_2.execute(
                    text("INSERT INTO test_rows (value) VALUES ('second')")
                )
                await session_2.commit()
                writer_finished.set()

        writer_task = asyncio.create_task(writer_2())

        await writer_started.wait()
        await asyncio.sleep(0.05)
        assert not writer_finished.is_set()

        await session_1.commit()
        await writer_task

    async with session_factory() as session:
        row_count = (
            await session.execute(text("SELECT COUNT(*) FROM test_rows"))
        ).scalar_one()

    assert row_count == 2

    await engine.dispose()
