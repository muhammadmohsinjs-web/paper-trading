from dataclasses import asdict

from fastapi.encoders import jsonable_encoder

from app.market.data_store import Candle, DataStore
from app.scanner.scanner import OpportunityScanner


def test_scan_payload_uses_json_safe_indicator_values(data_store) -> None:
    store = DataStore.get_instance()
    base_t = 1_700_000_000_000
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]

    for s_idx, symbol in enumerate(symbols):
        candles: list[Candle] = []
        base_price = 100.0 + s_idx * 15.0
        for i in range(220):
            close = base_price + i * (0.3 + s_idx * 0.04)
            candles.append(
                Candle(
                    open_time=base_t + i * 3_600_000,
                    open=close - 1.0,
                    high=close + 2.0,
                    low=close - 2.0,
                    close=close,
                    volume=1_000.0 + i * 6.0,
                )
            )
        store.set_candles(symbol, "1h", candles)

    scanner = OpportunityScanner(symbols=symbols)
    ranked = scanner.rank_symbols(interval="1h", max_results=5, liquidity_floor_usdt=0.0)
    scan_result = scanner.scan(interval="1h", max_results=50)

    payload = {
        "scanned_at": scan_result.scanned_at,
        "symbols_scanned": scan_result.symbols_scanned,
        "regime": scan_result.regime,
        "ranked_symbols": [asdict(item) for item in ranked],
        "opportunities": [asdict(item) for item in scan_result.opportunities],
    }

    encoded = jsonable_encoder(payload)

    widening = next(
        (
            item["indicators"]["widening"]
            for item in encoded["opportunities"]
            if "widening" in item["indicators"]
        ),
        None,
    )

    assert encoded["opportunities"]
    assert isinstance(widening, bool)
