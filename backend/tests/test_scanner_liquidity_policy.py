from types import SimpleNamespace

from app.engine.tradability import TradabilityMetrics, TradabilityResult
from app.market.data_store import Candle, DataStore
from app.regime.types import MarketRegime
from app.scanner.scanner import OpportunityScanner
from app.scanner.types import RankedSetup


def test_estimate_liquidity_usdt_returns_total_quote_volume(data_store) -> None:
    candles = [
        Candle(open_time=1, open=1.0, high=1.0, low=1.0, close=10.0, volume=100.0),
        Candle(open_time=2, open=1.0, high=1.0, low=1.0, close=10.0, volume=200.0),
    ]

    assert OpportunityScanner._estimate_liquidity_usdt(candles, window=2) == 3_000.0


def test_rank_symbols_keeps_small_alt_with_healthy_daily_and_hourly_liquidity(data_store, monkeypatch) -> None:
    store = DataStore.get_instance()
    candles = [
        Candle(
            open_time=1_700_000_000_000 + i * 3_600_000,
            open=1.0,
            high=1.02,
            low=0.98,
            close=1.0,
            volume=200_000.0,
        )
        for i in range(200)
    ]
    store.set_candles("RENDERUSDT", "1h", candles)

    tradability_result = TradabilityResult(
        passed=True,
        reason_codes=[],
        blocking_reason_codes=[],
        advisory_reason_codes=[],
        reason_text="passed",
        metrics=TradabilityMetrics(
            volume_24h_usdt=4_800_000.0,
            market_quality_score=0.82,
            reward_to_cost_ratio=2.4,
        ),
        market_quality_score=0.82,
    )

    monkeypatch.setattr("app.scanner.scanner.evaluate_symbol_tradability", lambda **kwargs: tradability_result)

    def fake_detect_setups(self, symbol, indicators, regime, **kwargs):
        return [
            RankedSetup(
                symbol=symbol,
                score=0.82,
                setup_type="ema_trend_bullish",
                signal="BUY",
                regime=regime.value,
                recommended_strategy="sma_crossover",
                reason="synthetic setup",
                liquidity_usdt=4_800_000.0,
                market_quality_score=0.82,
                reward_to_cost_ratio=2.4,
                volatility_quality_score=0.7,
                entry_eligible=True,
                symbol_quality_score=0.7,
                execution_quality_score=0.68,
                room_to_move_score=0.72,
                freshness_score=0.8,
            )
        ], []

    scanner = OpportunityScanner(symbols=["RENDERUSDT"])
    scanner.regime_classifier = SimpleNamespace(
        classify_full=lambda indicators: SimpleNamespace(
            regime=MarketRegime.TRENDING_UP,
            exhaustion_score=0.0,
        )
    )
    monkeypatch.setattr(OpportunityScanner, "_detect_setups", fake_detect_setups)

    ranked = scanner.rank_symbols(interval="1h", max_results=5)
    audit = scanner.get_last_rank_audit()

    assert [item.symbol for item in ranked] == ["RENDERUSDT"]
    assert audit
    assert audit[0]["status"] == "qualified"
