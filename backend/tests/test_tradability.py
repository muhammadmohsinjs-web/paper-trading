from decimal import Decimal

from app.engine.tradability import (
    TradabilityMetrics,
    evaluate_execution_liquidity,
    split_tradability_reason_codes,
)
from app.market.binance_rest import OrderBookSnapshot


def test_split_tradability_reason_codes_separates_blocking_from_advisory():
    blocking, advisory = split_tradability_reason_codes(
        [
            "MARKET_QUALITY_TOO_LOW",
            "MOVE_BELOW_COST",
            "NEAR_PEG_PROFILE",
            "LIQUIDITY_TOO_LOW",
        ]
    )

    assert blocking == ["NEAR_PEG_PROFILE", "LIQUIDITY_TOO_LOW"]
    assert advisory == ["MARKET_QUALITY_TOO_LOW", "MOVE_BELOW_COST"]


def test_execution_liquidity_passes_for_small_order_in_healthy_market():
    result = evaluate_execution_liquidity(
        metrics=TradabilityMetrics(volume_24h_usdt=2_500_000.0),
        estimated_notional=Decimal("500"),
    )

    assert result.passed is True
    assert result.reason_code is None


def test_execution_liquidity_rejects_when_order_share_of_volume_is_too_large():
    result = evaluate_execution_liquidity(
        metrics=TradabilityMetrics(volume_24h_usdt=400_000.0),
        estimated_notional=Decimal("10_000"),
    )

    assert result.passed is False
    assert result.reason_code in {"LIQUIDITY_EXECUTION_RISK", "LIQUIDITY_PARTICIPATION_TOO_HIGH"}


def test_execution_liquidity_rejects_when_spread_is_too_wide_for_tier():
    result = evaluate_execution_liquidity(
        metrics=TradabilityMetrics(volume_24h_usdt=60_000_000.0),
        estimated_notional=Decimal("1_000"),
        microstructure=OrderBookSnapshot(
            symbol="BTCUSDT",
            bid_price=100.0,
            ask_price=100.25,
            mid_price=100.125,
            spread_bps=24.97,
            bid_depth_usdt=50_000.0,
            ask_depth_usdt=50_000.0,
            depth_band_bps=35.0,
            depth_levels=20,
        ),
    )

    assert result.passed is False
    assert result.reason_code == "ORDER_BOOK_SPREAD_TOO_WIDE"


def test_execution_liquidity_rejects_when_near_mid_depth_is_too_thin():
    result = evaluate_execution_liquidity(
        metrics=TradabilityMetrics(volume_24h_usdt=12_000_000.0),
        estimated_notional=Decimal("2_000"),
        microstructure=OrderBookSnapshot(
            symbol="DOGEUSDT",
            bid_price=0.1,
            ask_price=0.1001,
            mid_price=0.10005,
            spread_bps=9.99,
            bid_depth_usdt=7_000.0,
            ask_depth_usdt=13_000.0,
            depth_band_bps=35.0,
            depth_levels=20,
        ),
    )

    assert result.passed is False
    assert result.reason_code == "ORDER_BOOK_DEPTH_TOO_THIN"


def test_execution_liquidity_uses_microstructure_as_borderline_advisory():
    result = evaluate_execution_liquidity(
        metrics=TradabilityMetrics(volume_24h_usdt=15_000_000.0),
        estimated_notional=Decimal("1_000"),
        microstructure=OrderBookSnapshot(
            symbol="ADAUSDT",
            bid_price=1.0,
            ask_price=1.0026,
            mid_price=1.0013,
            spread_bps=25.97,
            bid_depth_usdt=10_000.0,
            ask_depth_usdt=9_000.0,
            depth_band_bps=35.0,
            depth_levels=20,
        ),
    )

    assert result.passed is True
    assert result.advisory is True
    assert result.microstructure_available is True
