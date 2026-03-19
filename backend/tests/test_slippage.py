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


def test_small_order_slippage_is_deterministic():
    """Under $10k should produce the same midpoint rate every time."""
    price = Decimal("50000")
    notional = Decimal("5000")
    results = set()
    for _ in range(10):
        _, slippage = apply_slippage(price, notional, TradeSide.BUY)
        results.add(slippage)
    # Deterministic: all results should be identical
    assert len(results) == 1


def test_small_order_slippage_rate():
    """Under $10k midpoint: (0.01% + 0.05%) / 2 = 0.03%."""
    price = Decimal("50000")
    notional = Decimal("5000")
    _, slippage = apply_slippage(price, notional, TradeSide.BUY)
    rate = slippage / price
    # Midpoint of 0.0001 and 0.0005 = 0.0003
    assert abs(rate - Decimal("0.0003")) < Decimal("0.00001")


def test_large_order_higher_slippage():
    """$50k+ orders should have higher slippage than small orders."""
    price = Decimal("50000")
    _, small_slip = apply_slippage(price, Decimal("5000"), TradeSide.BUY)
    _, large_slip = apply_slippage(price, Decimal("100000"), TradeSide.BUY)
    assert large_slip > small_slip
