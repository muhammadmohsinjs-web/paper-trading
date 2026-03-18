from app.market.binance_ws import BinanceWSClient
from app.market.data_store import Candle


def test_format_live_price_log_plain_text_without_ansi() -> None:
    client = BinanceWSClient(symbol="BTCUSDT", interval="5m")
    first_candle = Candle(
        open_time=1700000000000,
        open=50000.0,
        high=50010.0,
        low=49990.0,
        close=50000.0,
        volume=123.0,
    )
    second_candle = Candle(
        open_time=1700000300000,
        open=50000.0,
        high=50020.0,
        low=49995.0,
        close=50012.5,
        volume=150.0,
    )

    first_message = client._format_live_price_log("BTCUSDT", first_candle, use_color=False)
    second_message = client._format_live_price_log("BTCUSDT", second_candle, use_color=False)

    assert "\033[" not in first_message
    assert "\033[" not in second_message
    assert "[LIVE] BTCUSDT/5m price=50,000.00 change=NEW" in first_message
    assert "price=50,012.50 change=+12.50" in second_message
    assert "candle_open=2023-11-14 22:13:20 UTC" in first_message
