"""Seed default strategy configurations into the database."""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_database
from app.models.strategy import Strategy
from app.models.wallet import Wallet

STRATEGIES = [
    {
        "name": "SMA Crossover (10/50)",
        "description": "Buy when SMA-10 crosses above SMA-50, sell on death cross. Classic trend-following strategy.",
        "config_json": {
            "strategy_type": "sma_crossover",
            "sma_short": 10,
            "sma_long": 50,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
    {
        "name": "SMA Crossover (5/20) Fast",
        "description": "Faster SMA crossover with 5/20 periods. More trades, quicker reaction to trends.",
        "config_json": {
            "strategy_type": "sma_crossover",
            "sma_short": 5,
            "sma_long": 20,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
    {
        "name": "SMA Crossover (20/100) Slow",
        "description": "Conservative SMA crossover with 20/100 periods. Fewer but more reliable signals.",
        "config_json": {
            "strategy_type": "sma_crossover",
            "sma_short": 20,
            "sma_long": 100,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
]


async def seed():
    await init_database()

    async with SessionLocal() as session:
        for s in STRATEGIES:
            strategy_id = str(uuid4())
            initial = Decimal(str(s["config_json"]["initial_balance"]))

            strategy = Strategy(
                id=strategy_id,
                name=s["name"],
                description=s["description"],
                config_json=s["config_json"],
                is_active=False,
            )
            wallet = Wallet(
                id=str(uuid4()),
                strategy_id=strategy_id,
                initial_balance_usdt=initial,
                available_usdt=initial,
            )
            session.add(strategy)
            session.add(wallet)
            print(f"  Created: {s['name']} ({strategy_id})")

        await session.commit()
    print("\nSeeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
