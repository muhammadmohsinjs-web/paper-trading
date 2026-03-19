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
        "description": "Buy when SMA-10 crosses above SMA-50, sell on death cross. Classic trend-following with volume confirmation.",
        "config_json": {
            "strategy_type": "sma_crossover",
            "sma_short": 10,
            "sma_long": 50,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
    {
        "name": "RSI Mean Reversion",
        "description": "Buy when RSI drops below 30 (oversold), sell when RSI rises above 70 (overbought). Catches reversals.",
        "config_json": {
            "strategy_type": "rsi_mean_reversion",
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
    {
        "name": "MACD Momentum",
        "description": "Buy on MACD bullish crossover (MACD crosses above signal line), sell on bearish crossover. Momentum-based.",
        "config_json": {
            "strategy_type": "macd_momentum",
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
    {
        "name": "Bollinger Bounce",
        "description": "Buy when price touches lower Bollinger Band, sell at upper band. Mean-reversion on volatility bands.",
        "config_json": {
            "strategy_type": "bollinger_bounce",
            "bb_period": 20,
            "bb_std_dev": 2.0,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    },
    {
        "name": "Hybrid AI Composite",
        "description": "Combines RSI, MACD, SMA, EMA, Volume + AI advisor. Weighted composite scoring with confidence gates.",
        "config_json": {
            "strategy_type": "hybrid_composite",
            "initial_balance": 1000,
            "interval_seconds": 300,
            "sma_short": 10,
            "sma_long": 50,
            "confidence_gate": 0.5,
            "ai_enabled": True,
            "ai_cooldown_seconds": 300,
            "ai_max_tokens": 700,
            "ai_temperature": 0.2,
        },
        "ai_enabled": True,
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
                ai_enabled=s.get("ai_enabled", False),
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
