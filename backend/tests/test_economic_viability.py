from decimal import Decimal

from app.engine.economic_viability import evaluate_economic_viability


def test_economic_viability_rejects_fee_negative_setup():
    result = evaluate_economic_viability(
        entry_price=Decimal("1.0000"),
        stop_loss_price=Decimal("0.9980"),
        take_profit_price=Decimal("1.0004"),
        fee_rate=Decimal("0.001"),
        entry_slippage_rate=Decimal("0.0003"),
        exit_slippage_rate=Decimal("0.0003"),
    )

    assert result.passed is False
    assert "NET_REWARD_NON_POSITIVE" in result.reason_codes
    assert "TP_BELOW_COST_BUFFER" in result.reason_codes


def test_economic_viability_accepts_post_cost_positive_setup():
    result = evaluate_economic_viability(
        entry_price=Decimal("100"),
        stop_loss_price=Decimal("98"),
        take_profit_price=Decimal("104"),
        fee_rate=Decimal("0.00075"),
        entry_slippage_rate=Decimal("0.0002"),
        exit_slippage_rate=Decimal("0.0002"),
    )

    assert result.passed is True
    assert result.net_reward_pct > 0.25
    assert result.net_rr >= 1.2
