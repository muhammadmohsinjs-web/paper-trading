"""Clear runtime paper-trading data while preserving strategy definitions."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_database
from app.db_maintenance import reset_runtime_data


async def cleanup(apply_changes: bool) -> int:
    await init_database()

    async with SessionLocal() as session:
        summary = await reset_runtime_data(session)

        if apply_changes:
            await session.commit()
        else:
            await session.rollback()

    mode = "applied" if apply_changes else "dry-run"
    print(f"Cleanup {mode}.")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove runtime paper-trading data while preserving strategies.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the cleanup. Without this flag the script runs as a dry run.",
    )
    args = parser.parse_args()
    return asyncio.run(cleanup(apply_changes=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
