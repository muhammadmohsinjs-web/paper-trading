"""Tests for multicoin shared-wallet helpers and persisted daily picks."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.engine.multi_coin import compute_total_equity, compute_unrealized_pnl, ensure_daily_picks
from app.market.data_store import Candle, DataStore
from app.models.symbol_evaluation_log import SymbolEvaluationLog
from app.models.strategy import Strategy
from app.scanner.types import RankedSymbol


@pytest.mark.asyncio
async def test_ensure_daily_picks_persists_top_five_and_reuses_same_day(db_session, monkeypatch):
    strategy = Strategy(
        id="multi-1",
        name="Multi Coin",
        execution_mode="multi_coin_shared_wallet",
        primary_symbol="BTCUSDT",
        scan_universe_json=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"],
        top_pick_count=5,
        config_json={},
    )
    db_session.add(strategy)
    await db_session.commit()

    calls = {"count": 0}

    def fake_rank_symbols(self, interval="1h", max_results=5, liquidity_floor_usdt=None):
        calls["count"] += 1
        return [
            RankedSymbol("BTCUSDT", 0.91, "trending_up", "volume_breakout", "macd_momentum", "btc", 2_000_000.0),
            RankedSymbol("ETHUSDT", 0.88, "trending_up", "volume_breakout", "macd_momentum", "eth", 2_000_000.0),
            RankedSymbol("SOLUSDT", 0.83, "trending_up", "bb_squeeze", "bollinger_bounce", "sol", 2_000_000.0),
            RankedSymbol("XRPUSDT", 0.79, "ranging", "rsi_oversold", "rsi_mean_reversion", "xrp", 2_000_000.0),
            RankedSymbol("BNBUSDT", 0.74, "trending_up", "sma_crossover_proximity", "sma_crossover", "bnb", 2_000_000.0),
        ][:max_results]

    monkeypatch.setattr("app.engine.multi_coin.OpportunityScanner.rank_symbols", fake_rank_symbols)

    first = await ensure_daily_picks(db_session, strategy, interval="1h")
    await db_session.commit()
    second = await ensure_daily_picks(db_session, strategy, interval="1h")

    assert calls["count"] == 1
    assert len(first) == 5
    assert [pick.rank for pick in first] == [1, 2, 3, 4, 5]
    assert [pick.symbol for pick in second] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
    assert all(pick.selection_date == datetime.now(timezone.utc).date() for pick in second)


@pytest.mark.asyncio
async def test_ensure_daily_picks_uses_dynamic_universe_when_strategy_has_no_explicit_universe(db_session, monkeypatch):
    strategy = Strategy(
        id="multi-dynamic-1",
        name="Dynamic Multi Coin",
        execution_mode="multi_coin_shared_wallet",
        primary_symbol="BTCUSDT",
        scan_universe_json=[],
        top_pick_count=2,
        config_json={},
    )
    db_session.add(strategy)
    await db_session.commit()

    calls = {"resolve_symbols": 0}

    async def fake_resolve_symbols(self, *, retained_symbols=None):
        calls["resolve_symbols"] += 1
        self.symbols = ["ETHUSDT", "SOLUSDT"]
        return self.symbols

    def fake_rank_symbols(self, interval="1h", max_results=5, liquidity_floor_usdt=None):
        assert self.symbols == ["ETHUSDT", "SOLUSDT"]
        return [
            RankedSymbol("ETHUSDT", 0.88, "trending_up", "volume_breakout", "macd_momentum", "eth", 2_000_000.0),
            RankedSymbol("SOLUSDT", 0.83, "trending_up", "bb_squeeze", "bollinger_bounce", "sol", 2_000_000.0),
        ][:max_results]

    monkeypatch.setattr("app.engine.multi_coin.OpportunityScanner.resolve_symbols", fake_resolve_symbols)
    monkeypatch.setattr("app.engine.multi_coin.OpportunityScanner.rank_symbols", fake_rank_symbols)

    picks = await ensure_daily_picks(
        db_session,
        strategy,
        interval="1h",
        open_position_symbols={"BTCUSDT"},
    )

    assert calls["resolve_symbols"] == 1
    assert [pick.symbol for pick in picks] == ["ETHUSDT", "SOLUSDT"]


def test_compute_total_equity_and_unrealized_pnl_sum_across_symbols(data_store):
    store = DataStore.get_instance()
    store.set_candles(
        "BTCUSDT",
        "1h",
        [Candle(open_time=1, open=50000, high=51000, low=49000, close=52000, volume=1000)],
    )
    store.set_candles(
        "ETHUSDT",
        "1h",
        [Candle(open_time=1, open=2500, high=2600, low=2400, close=2700, volume=1000)],
    )

    wallet = SimpleNamespace(available_usdt=Decimal("400"))
    positions = [
        SimpleNamespace(symbol="BTCUSDT", quantity=Decimal("0.01"), entry_price=Decimal("50000"), entry_fee=Decimal("2")),
        SimpleNamespace(symbol="ETHUSDT", quantity=Decimal("1.5"), entry_price=Decimal("2500"), entry_fee=Decimal("3")),
    ]

    total_equity = compute_total_equity(wallet, positions)
    unrealized_pnl = compute_unrealized_pnl(positions)

    assert total_equity == Decimal("400") + Decimal("520") + Decimal("4050")
    assert unrealized_pnl == Decimal("315")


@pytest.mark.asyncio
async def test_explicit_universe_logs_real_tradability(db_session):
    strategy = Strategy(
        id="multi-explicit-logs",
        name="Explicit Logs",
        execution_mode="multi_coin_shared_wallet",
        primary_symbol="BTCUSDT",
        scan_universe_json=["USDCUSDT"],
        top_pick_count=1,
        candle_interval="1h",
        config_json={"ai_enabled": False},
    )
    db_session.add(strategy)
    await db_session.commit()

    store = DataStore.get_instance()
    candles: list[Candle] = []
    base_t = 1_700_000_000_000
    for i in range(220):
        close = 1.0 + ((i % 2) * 0.0002)
        candles.append(
            Candle(
                open_time=base_t + i * 3_600_000,
                open=close,
                high=close + 0.0003,
                low=close - 0.0003,
                close=close,
                volume=5_000.0,
            )
        )
    store.set_candles("USDCUSDT", "1h", candles)

    await ensure_daily_picks(db_session, strategy, interval="1h", force_refresh=True)
    await db_session.commit()

    logs = (
        await db_session.execute(
            select(SymbolEvaluationLog)
            .where(
                SymbolEvaluationLog.strategy_id == strategy.id,
                SymbolEvaluationLog.stage == "universe_tradability",
            )
        )
    ).scalars().all()

    assert logs
    assert logs[0].status == "rejected"
    assert logs[0].reason_code in {"DENYLIST_STABLE_BASE", "NEAR_PEG_PROFILE"}
