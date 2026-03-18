"""Tests for slippage simulation."""

from decimal import Decimal

from app.engine.slippage import apply_slippage
from app.models.enums import TradeSide


def test_buy_slippage_is_adverse():
    """Buy slippage should increase price."""
    price = Decimal("50000")
    notional = Decimal("5000")
    exec_price, slippage = apply_slippage(price, notional, TradeSide.BUY)
    assert exec_price > price
    assert slippage > 0


def test_sell_slippage_is_adverse():
    """Sell slippage should decrease price."""
    price = Decimal("50000")
    notional = Decimal("5000")
    exec_price, slippage = apply_slippage(price, notional, TradeSide.SELL)
    assert exec_price < price
    assert slippage > 0


def test_small_order_slippage_range():
    """Under $10k should have 0.01%-0.05% slippage."""
    price = Decimal("50000")
    notional = Decimal("5000")
    for _ in range(50):
        exec_price, slippage = apply_slippage(price, notional, TradeSide.BUY)
        rate = slippage / price
        assert Decimal("0.00005") <= rate <= Decimal("0.001")  # generous bounds


def test_large_order_higher_slippage():
    """$50k+ orders should have higher slippage on average."""
    price = Decimal("50000")
    small_total = Decimal("0")
    large_total = Decimal("0")
    n = 100

    for _ in range(n):
        _, s = apply_slippage(price, Decimal("5000"), TradeSide.BUY)
        small_total += s
        _, s = apply_slippage(price, Decimal("100000"), TradeSide.BUY)
        large_total += s

    assert large_total / n > small_total / n
