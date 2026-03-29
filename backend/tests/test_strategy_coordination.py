from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.engine.conflict_resolver import PinnedSymbol, resolve_conflicts
from app.engine.multi_coin import ensure_coordinated_picks
from app.engine.strategy_scorer import (
    StrategyCandidate,
    evaluate_universe_for_strategy,
    get_strategy_profile,
)
from app.models.daily_pick import DailyPick
from app.models.strategy import Strategy
from app.models.symbol_ownership import SymbolOwnership
from app.regime.types import MarketRegime
from app.scanner.types import RankedSetup


def _candidate(
    strategy_id: str,
    strategy_name: str,
    strategy_type: str,
    symbol: str,
    score: float,
    *,
    regime: str = "ranging",
    setup_type: str = "rsi_oversold",
    recommended_strategy: str | None = None,
) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        symbol=symbol,
        final_score=score,
        regime=regime,
        setup_type=setup_type,
        recommended_strategy=recommended_strategy or strategy_type,
        assignment_reason=f"{symbol}:{strategy_type}",
        setup_fit_score=score,
        regime_fit_score=0.8,
        liquidity_score=0.7,
        perf_memory_score=0.5,
        vol_quality_score=0.6,
        expected_rr_score=0.7,
        liquidity_usdt=2_000_000.0,
        market_quality_score=0.8,
        reward_to_cost_ratio=2.0,
        movement_quality={},
    )


def test_strategy_scorer_filters_setup_types_and_regimes():
    strategy = Strategy(
        id="sma-1",
        name="SMA",
        execution_mode="multi_coin_shared_wallet",
        config_json={"strategy_type": "sma_crossover"},
    )
    profile = get_strategy_profile("sma_crossover")
    assert profile is not None

    result = evaluate_universe_for_strategy(
        strategy,
        profile,
        {
            "BTCUSDT": [RankedSetup("BTCUSDT", 0.82, "sma_crossover_proximity", "BUY", "trending_up", "sma_crossover", "trend", liquidity_usdt=2_000_000.0, market_quality_score=0.8, reward_to_cost_ratio=2.1, volatility_quality_score=0.7)],
            "ETHUSDT": [RankedSetup("ETHUSDT", 0.90, "rsi_oversold", "BUY", "ranging", "rsi_mean_reversion", "revert", liquidity_usdt=2_000_000.0, market_quality_score=0.8, reward_to_cost_ratio=2.1, volatility_quality_score=0.7)],
            "SOLUSDT": [RankedSetup("SOLUSDT", 0.78, "ema_trend_bullish", "BUY", "ranging", "sma_crossover", "hostile", liquidity_usdt=2_000_000.0, market_quality_score=0.8, reward_to_cost_ratio=2.1, volatility_quality_score=0.7)],
        },
        {
            "BTCUSDT": MarketRegime.TRENDING_UP,
            "ETHUSDT": MarketRegime.RANGING,
            "SOLUSDT": MarketRegime.RANGING,
        },
    )

    assert [candidate.symbol for candidate in result.candidates] == ["BTCUSDT"]
    assert {rejection.symbol for rejection in result.rejections} == {"ETHUSDT", "SOLUSDT"}


def test_strategy_scorer_keeps_exceptional_off_regime_setup_as_penalized_candidate():
    strategy = Strategy(
        id="sma-1",
        name="SMA",
        execution_mode="multi_coin_shared_wallet",
        config_json={"strategy_type": "sma_crossover"},
    )
    profile = get_strategy_profile("sma_crossover")
    assert profile is not None

    result = evaluate_universe_for_strategy(
        strategy,
        profile,
        {
            "SOLUSDT": [
                RankedSetup(
                    "SOLUSDT",
                    0.88,
                    "ema_trend_bullish",
                    "BUY",
                    "ranging",
                    "sma_crossover",
                    "exceptional",
                    liquidity_usdt=2_000_000.0,
                    market_quality_score=0.8,
                    reward_to_cost_ratio=2.1,
                    volatility_quality_score=0.7,
                    symbol_quality_score=0.74,
                    execution_quality_score=0.69,
                )
            ],
        },
        {"SOLUSDT": MarketRegime.RANGING},
    )

    assert [candidate.symbol for candidate in result.candidates] == ["SOLUSDT"]
    assert result.rejections == []


def test_conflict_resolver_respects_tiebreak_and_cooldown():
    now = datetime.now(timezone.utc)
    assignments, rejections = resolve_conflicts(
        {
            "hybrid-1": [_candidate("hybrid-1", "Hybrid", "hybrid_composite", "BTCUSDT", 0.9, recommended_strategy="macd_momentum")],
            "macd-1": [_candidate("macd-1", "MACD", "macd_momentum", "BTCUSDT", 0.9)],
            "rsi-1": [_candidate("rsi-1", "RSI", "rsi_mean_reversion", "ETHUSDT", 0.8)],
        },
        pinned_symbols={
            "SOLUSDT": PinnedSymbol(strategy_id="macd-1", strategy_name="MACD", strategy_type="macd_momentum", symbol="SOLUSDT")
        },
        cooldowns={("rsi-1", "ETHUSDT"): now + timedelta(minutes=10)},
        per_strategy_max={"hybrid-1": 2, "macd-1": 2, "rsi-1": 2},
        global_max=5,
        now=now,
    )

    assert [candidate.symbol for candidate in assignments["hybrid-1"]] == ["BTCUSDT"]
    assert [candidate.symbol for candidate in assignments["macd-1"]] == ["SOLUSDT"]
    assert assignments["rsi-1"] == []
    assert {rejection.reason_code for rejection in rejections} >= {"CONFLICT_LOST_TIEBREAK", "COOLDOWN_ACTIVE"}


@pytest.mark.asyncio
async def test_ensure_coordinated_picks_assigns_exclusive_symbols_and_writes_ownership(db_session, monkeypatch):
    macd = Strategy(
        id="macd-1",
        name="MACD",
        execution_mode="multi_coin_shared_wallet",
        is_active=True,
        top_pick_count=2,
        config_json={"strategy_type": "macd_momentum"},
    )
    rsi = Strategy(
        id="rsi-1",
        name="RSI",
        execution_mode="multi_coin_shared_wallet",
        is_active=True,
        top_pick_count=2,
        config_json={"strategy_type": "rsi_mean_reversion"},
    )
    db_session.add_all([macd, rsi])
    await db_session.commit()

    def fake_scan_all_setups(self, interval="1h"):
        self._last_rank_audit = []
        self._last_regime_cache = {
            "BTCUSDT": MarketRegime.TRENDING_DOWN,
            "ETHUSDT": MarketRegime.RANGING,
        }
        return {
            "BTCUSDT": [RankedSetup("BTCUSDT", 0.92, "adx_strong_trend", "SELL", "trending_down", "rsi_mean_reversion", "shared", liquidity_usdt=2_500_000.0, market_quality_score=0.8, reward_to_cost_ratio=2.3, volatility_quality_score=0.8)],
            "ETHUSDT": [RankedSetup("ETHUSDT", 0.88, "rsi_oversold", "BUY", "ranging", "rsi_mean_reversion", "exclusive", liquidity_usdt=2_500_000.0, market_quality_score=0.8, reward_to_cost_ratio=2.3, volatility_quality_score=0.8)],
        }

    monkeypatch.setattr("app.engine.multi_coin.OpportunityScanner.scan_all_setups_for_universe", fake_scan_all_setups)
    monkeypatch.setattr("app.engine.multi_coin.OpportunityScanner.get_last_regime_cache", lambda self: self._last_regime_cache)

    async def fake_resolve_symbols(self, *, retained_symbols=None):
        return self.symbols

    monkeypatch.setattr("app.engine.multi_coin.OpportunityScanner.resolve_symbols", fake_resolve_symbols)

    await ensure_coordinated_picks(
        db_session,
        [macd, rsi],
        interval="1h",
    )
    await db_session.commit()

    picks = (
        await db_session.execute(
            select(DailyPick).order_by(DailyPick.strategy_id.asc(), DailyPick.rank.asc())
        )
    ).scalars().all()
    ownerships = (
        await db_session.execute(
            select(SymbolOwnership).where(SymbolOwnership.released_at.is_(None)).order_by(SymbolOwnership.symbol.asc())
        )
    ).scalars().all()

    assert [(pick.strategy_id, pick.symbol) for pick in picks] == [("macd-1", "BTCUSDT"), ("rsi-1", "ETHUSDT")]
    assert [ownership.symbol for ownership in ownerships] == ["BTCUSDT", "ETHUSDT"]
    assert len({ownership.symbol for ownership in ownerships}) == len(ownerships)
