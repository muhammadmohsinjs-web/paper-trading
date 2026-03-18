"""Tests for fee calculation."""

from decimal import Decimal

from app.engine.fee_model import BNB_DISCOUNT_RATE, SPOT_FEE_RATE, calculate_fee


def test_spot_fee_1000_usdt():
    fee = calculate_fee(Decimal("1000"), SPOT_FEE_RATE)
    assert fee == Decimal("1.00000000")


def test_spot_fee_500_usdt():
    fee = calculate_fee(Decimal("500"), SPOT_FEE_RATE)
    assert fee == Decimal("0.50000000")


def test_bnb_discount_fee():
    fee = calculate_fee(Decimal("1000"), BNB_DISCOUNT_RATE)
    assert fee == Decimal("0.75000000")


def test_round_trip_fee():
    """Buy + sell at same notional should cost 0.20% total."""
    notional = Decimal("10000")
    buy_fee = calculate_fee(notional, SPOT_FEE_RATE)
    sell_fee = calculate_fee(notional, SPOT_FEE_RATE)
    total = buy_fee + sell_fee
    expected = Decimal("20.00000000")  # 0.20% of 10k
    assert total == expected


def test_zero_notional():
    fee = calculate_fee(Decimal("0"), SPOT_FEE_RATE)
    assert fee == Decimal("0E-8")
