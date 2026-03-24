from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db_maintenance import reset_runtime_data
from app.models.ai_call_log import AICallLog
from app.models.enums import PositionSide, TradeSide
from app.models.position import Position
from app.models.price_cache import PriceCache
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.wallet import Wallet


@pytest.mark.asyncio
async def test_reset_runtime_data_keeps_strategies_and_rebuilds_wallets(db_session):
    strategy_one = Strategy(
        id="strategy-one",
        name="Strategy One",
        config_json={"initial_balance": 2500},
        is_active=True,
        ai_enabled=True,
        ai_last_decision_at=datetime.now(timezone.utc),
        ai_last_decision_status="signal",
        ai_last_reasoning="buy",
        ai_last_provider="openai",
        ai_last_model="gpt-test",
        ai_last_prompt_tokens=123,
        ai_last_completion_tokens=45,
        ai_last_total_tokens=168,
        ai_last_cost_usdt=Decimal("1.25"),
        ai_total_calls=9,
        ai_total_prompt_tokens=900,
        ai_total_completion_tokens=450,
        ai_total_tokens=1350,
        ai_total_cost_usdt=Decimal("10.50"),
        consecutive_losses=3,
        max_consecutive_losses=4,
        streak_size_multiplier=Decimal("0.5"),
    )
    strategy_two = Strategy(
        id="strategy-two",
        name="Strategy Two",
        config_json={},
        is_active=False,
    )
    db_session.add_all([strategy_one, strategy_two])
    await db_session.flush()

    db_session.add_all(
        [
            Wallet(
                id="wallet-one",
                strategy_id=strategy_one.id,
                initial_balance_usdt=Decimal("2500"),
                available_usdt=Decimal("1800"),
                peak_equity_usdt=Decimal("2700"),
            ),
            Wallet(
                id="wallet-two",
                strategy_id=strategy_two.id,
                initial_balance_usdt=Decimal("1000"),
                available_usdt=Decimal("850"),
                peak_equity_usdt=Decimal("1200"),
            ),
            Position(
                id="position-one",
                strategy_id=strategy_one.id,
                symbol="BTCUSDT",
                side=PositionSide.LONG,
                quantity=Decimal("0.01"),
                entry_price=Decimal("80000"),
                entry_fee=Decimal("1"),
            ),
            Trade(
                id="trade-one",
                strategy_id=strategy_one.id,
                symbol="BTCUSDT",
                side=TradeSide.BUY,
                quantity=Decimal("0.01"),
                price=Decimal("80000"),
                market_price=Decimal("80000"),
                fee=Decimal("1"),
                slippage=Decimal("0"),
                strategy_name="Strategy One",
                strategy_type="sma_crossover",
            ),
            Snapshot(
                strategy_id=strategy_one.id,
                total_equity_usdt=Decimal("2501"),
            ),
            AICallLog(
                id="ai-log-one",
                strategy_id=strategy_one.id,
                symbol="BTCUSDT",
                status="signal",
                action="buy",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                cost_usdt=Decimal("0.25"),
            ),
            PriceCache(
                symbol="BTCUSDT",
                interval="1h",
                open_time=1,
                open=Decimal("1"),
                high=Decimal("2"),
                low=Decimal("0.5"),
                close=Decimal("1.5"),
                volume=Decimal("100"),
            ),
        ]
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE strategy_cycle_locks (
                strategy_id VARCHAR(36) PRIMARY KEY,
                owner_id VARCHAR(64) NOT NULL,
                acquired_at DATETIME NOT NULL
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO strategy_cycle_locks (strategy_id, owner_id, acquired_at)
            VALUES ('strategy-one', 'worker-1', CURRENT_TIMESTAMP)
            """
        )
    )
    await db_session.commit()

    summary = await reset_runtime_data(db_session)
    await db_session.commit()

    assert summary["strategies"] == 2
    assert summary["wallets"] == 2
    assert summary["positions"] == 1
    assert summary["trades"] == 1
    assert summary["snapshots"] == 1
    assert summary["ai_call_logs"] == 1
    assert summary["price_cache"] == 1
    assert summary["strategy_cycle_locks"] == 1
    assert summary["wallets_recreated"] == 2

    strategies = list(
        (
            await db_session.execute(
                select(Strategy)
                .options(selectinload(Strategy.wallet))
                .order_by(Strategy.id.asc())
            )
        ).scalars()
    )
    assert [strategy.id for strategy in strategies] == ["strategy-one", "strategy-two"]
    assert [strategy.wallet.initial_balance_usdt for strategy in strategies] == [
        Decimal("2500"),
        Decimal("1000"),
    ]
    assert [strategy.wallet.available_usdt for strategy in strategies] == [
        Decimal("2500"),
        Decimal("1000"),
    ]
    assert strategies[0].is_active is True
    assert strategies[0].ai_last_decision_at is None
    assert strategies[0].ai_last_decision_status is None
    assert strategies[0].ai_last_reasoning is None
    assert strategies[0].ai_last_provider is None
    assert strategies[0].ai_last_model is None
    assert strategies[0].ai_last_prompt_tokens == 0
    assert strategies[0].ai_last_completion_tokens == 0
    assert strategies[0].ai_last_total_tokens == 0
    assert strategies[0].ai_last_cost_usdt == Decimal("0")
    assert strategies[0].ai_total_calls == 0
    assert strategies[0].ai_total_prompt_tokens == 0
    assert strategies[0].ai_total_completion_tokens == 0
    assert strategies[0].ai_total_tokens == 0
    assert strategies[0].ai_total_cost_usdt == Decimal("0")
    assert strategies[0].consecutive_losses == 0
    assert strategies[0].max_consecutive_losses == 0
    assert strategies[0].streak_size_multiplier == Decimal("1.0")

    assert (await db_session.execute(select(Trade))).scalars().all() == []
    assert (await db_session.execute(select(Position))).scalars().all() == []
    assert (await db_session.execute(select(Snapshot))).scalars().all() == []
    assert (await db_session.execute(select(AICallLog))).scalars().all() == []
    assert (await db_session.execute(select(PriceCache))).scalars().all() == []
    assert (
        await db_session.execute(text("SELECT COUNT(*) FROM strategy_cycle_locks"))
    ).scalar_one() == 0
