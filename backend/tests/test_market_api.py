from app.api.market import _build_indicator_payload


def test_build_indicator_payload_returns_aligned_series(make_candles) -> None:
    candles = make_candles(count=160, trend=18.0, volatility=70.0)

    payload = _build_indicator_payload(
        "BTCUSDT",
        "1h",
        candles,
        {
            "sma_short": 20,
            "sma_long": 50,
            "rsi_period": 14,
            "volume_ma_period": 20,
        },
    )

    assert payload["symbol"] == "BTCUSDT"
    assert payload["interval"] == "1h"
    assert payload["candles_used"] == 160
    assert payload["config"]["sma_short"] == 20
    assert payload["config"]["sma_long"] == 50
    assert payload["latest"]["price"] == round(candles[-1].close, 4)

    sma_short = payload["series"]["sma_short"]
    macd_line = payload["series"]["macd_line"]
    volume_ratio = payload["series"]["volume_ratio"]

    assert sma_short
    assert macd_line
    assert volume_ratio

    assert sma_short[0]["open_time"] == candles[-len(sma_short)].open_time
    assert sma_short[-1]["open_time"] == candles[-1].open_time
    assert macd_line[-1]["open_time"] == candles[-1].open_time
    assert volume_ratio[-1]["open_time"] == candles[-1].open_time
