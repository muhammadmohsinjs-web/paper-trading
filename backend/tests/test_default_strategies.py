from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.default_strategies import sync_default_strategies
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.models.wallet import Wallet


def _strategy_type(strategy: Strategy) -> str:
    return str((strategy.config_json or {}).get("strategy_type") or "")


@pytest.mark.asyncio
async def test_sync_default_strategies_upserts_legacy_rows_without_resetting_wallet(db_session):
    legacy = Strategy(
        id="legacy-sma",
        name="SMA Crossover",
        description="old row",
        config_json={
            "strategy_type": "sma_crossover",
            "sma_short": 5,
            "sma_long": 20,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
        is_active=False,
        execution_mode="single_symbol",
        primary_symbol="BTCUSDT",
    )
    wallet = Wallet(
        id="wallet-1",
        strategy_id=legacy.id,
        initial_balance_usdt=Decimal("1000"),
        available_usdt=Decimal("812.34"),
        peak_equity_usdt=Decimal("1000"),
    )
    db_session.add_all([legacy, wallet])
    await db_session.commit()

    report = await sync_default_strategies(db_session)

    result = await db_session.execute(select(Strategy).order_by(Strategy.name.asc()))
    strategies = list(result.scalars().all())
    default_strategy_names = {
        "SMA Crossover (10/50)",
        "RSI Mean Reversion",
        "MACD Momentum",
        "Bollinger Bounce",
        "Hybrid AI Composite",
    }
    default_strategies = [strategy for strategy in strategies if strategy.name in default_strategy_names]

    assert report == {"created": 4, "updated": 1, "duplicates": 0}
    assert len(default_strategies) == 5

    sma = next(strategy for strategy in default_strategies if _strategy_type(strategy) == "sma_crossover")
    assert sma.id == "legacy-sma"
    assert sma.name == "SMA Crossover (10/50)"
    assert sma.execution_mode == "multi_coin_shared_wallet"
    assert sma.top_pick_count == 5
    assert sma.max_concurrent_positions == 2
    assert sma.is_active is True

    wallet_result = await db_session.execute(
        select(Wallet).where(Wallet.strategy_id == sma.id)
    )
    synced_wallet = wallet_result.scalar_one()
    assert synced_wallet.available_usdt == Decimal("812.34")

    snapshot_result = await db_session.execute(
        select(Snapshot).where(Snapshot.strategy_id == sma.id)
    )
    snapshot = snapshot_result.scalar_one_or_none()
    assert snapshot is not None


@pytest.mark.asyncio
async def test_sync_default_strategies_reports_duplicates_without_creating_more(db_session):
    db_session.add_all(
        [
            Strategy(
                id="macd-1",
                name="MACD Momentum",
                config_json={"strategy_type": "macd_momentum", "initial_balance": 1000},
            ),
            Strategy(
                id="macd-2",
                name="MACD Momentum",
                config_json={"strategy_type": "macd_momentum", "initial_balance": 1000},
            ),
        ]
    )
    await db_session.commit()

    report = await sync_default_strategies(db_session)

    result = await db_session.execute(select(Strategy))
    strategies = list(result.scalars().all())
    macd_rows = [strategy for strategy in strategies if _strategy_type(strategy) == "macd_momentum"]

    assert report["duplicates"] == 1
    assert len(macd_rows) == 2
