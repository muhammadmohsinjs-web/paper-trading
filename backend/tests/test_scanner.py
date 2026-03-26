from dataclasses import asdict

from fastapi.encoders import jsonable_encoder

from app.market.data_store import Candle, DataStore
from app.scanner.scanner import OpportunityScanner
from app.scanner.types import RankedSetup, RankedSymbol


def test_scan_payload_uses_json_safe_indicator_values(data_store) -> None:
    payload = {
        "scanned_at": "2026-03-26T00:00:00Z",
        "symbols_scanned": 1,
        "regime": "trending_up",
        "ranked_symbols": [
            asdict(
                RankedSymbol(
                    symbol="BTCUSDT",
                    score=0.91,
                    regime="trending_up",
                    setup_type="ema_trend_bullish",
                    recommended_strategy="sma_crossover",
                    reason="synthetic",
                    liquidity_usdt=2_000_000.0,
                    indicators={"widening": True, "ema_spread_pct": 0.5},
                )
            )
        ],
        "opportunities": [
            asdict(
                RankedSetup(
                    symbol="BTCUSDT",
                    score=0.91,
                    setup_type="ema_trend_bullish",
                    signal="BUY",
                    regime="trending_up",
                    recommended_strategy="sma_crossover",
                    reason="synthetic",
                    indicators={"widening": True, "ema_spread_pct": 0.5},
                )
            )
        ],
    }

    encoded = jsonable_encoder(payload)

    combined = encoded["opportunities"] or encoded["ranked_symbols"]
    widening = next(
        (
            item["indicators"]["widening"]
            for item in combined
            if "widening" in item.get("indicators", {})
        ),
        None,
    )

    assert combined
    assert isinstance(widening, bool)


def test_rank_symbols_rejects_near_peg_symbol(data_store) -> None:
    store = DataStore.get_instance()
    base_t = 1_700_000_000_000
    candles: list[Candle] = []
    for i in range(220):
        close = 1.0 + ((i % 2) * 0.0002)
        candles.append(
            Candle(
                open_time=base_t + i * 3_600_000,
                open=close,
                high=close + 0.0003,
                low=close - 0.0003,
                close=close,
                volume=8_000.0,
            )
        )
    store.set_candles("USD1USDT", "1h", candles)

    scanner = OpportunityScanner(symbols=["USD1USDT"])
    ranked = scanner.rank_symbols(interval="1h", max_results=5, liquidity_floor_usdt=0.0)
    audit = scanner.get_last_rank_audit()

    assert ranked == []
    assert audit
    assert audit[0]["status"] == "rejected"
    assert audit[0]["reason_code"] in {"DENYLIST_STABLE_BASE", "NEAR_PEG_PROFILE"}
