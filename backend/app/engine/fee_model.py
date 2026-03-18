"""Binance-realistic fee calculation."""

from __future__ import annotations

from decimal import Decimal

# Default Binance spot fee rates
SPOT_FEE_RATE = Decimal("0.001")  # 0.10%
BNB_DISCOUNT_RATE = Decimal("0.00075")  # 0.075%


def calculate_fee(
    notional: Decimal,
    fee_rate: Decimal = SPOT_FEE_RATE,
) -> Decimal:
    """Calculate trading fee for a given notional value.

    Args:
        notional: Total trade value in quote currency (price * quantity).
        fee_rate: Fee rate to apply. Defaults to Binance spot 0.1%.

    Returns:
        Fee amount in quote currency.
    """
    return (notional * fee_rate).quantize(Decimal("0.00000001"))
