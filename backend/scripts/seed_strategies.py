"""Sync the built-in strategy catalog into the database."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_database
from app.default_strategies import replace_default_strategies, sync_default_strategies


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync or replace the built-in strategy catalog.",
    )
    parser.add_argument(
        "--replace-defaults",
        action="store_true",
        help="Delete built-in strategies first, then recreate the canonical set.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await init_database()

    async with SessionLocal() as session:
        if args.replace_defaults:
            report = await replace_default_strategies(session)
            print(
                "Replaced built-in strategies: "
                f"removed={report['removed']} created={report['created']}"
            )
        else:
            report = await sync_default_strategies(session)
            print(
                "Synced built-in strategies: "
                f"created={report['created']} updated={report['updated']} duplicates={report['duplicates']}"
            )
            if report["duplicates"]:
                print(
                    "Duplicate built-in strategies were detected and left in place. "
                    "Use --replace-defaults if you want a clean canonical reset."
                )


if __name__ == "__main__":
    asyncio.run(main())
