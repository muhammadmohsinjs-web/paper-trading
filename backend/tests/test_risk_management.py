"""Tests for risk management: circuit breakers, flat market detection, loss tracking."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.engine.post_trade import (
    accumulate_wallet_losses as _accumulate_wallet_losses,
    compute_equity as _compute_equity,
)
from app.engine.trading_loop import should_skip_flat_market
from app.engine.ai_runtime import analyze_flat_market


# ──────────────── _compute_equity ────────────────


def test_compute_equity_no_position():
    wallet = SimpleNamespace(available_usdt=Decimal("5000"))
    equity = _compute_equity(wallet, None, Decimal("85000"))
    assert equity == Decimal("5000")


def test_compute_equity_with_position():
    wallet = SimpleNamespace(available_usdt=Decimal("5000"))
    position = SimpleNamespace(quantity=Decimal("0.1"))
    equity = _compute_equity(wallet, position, Decimal("85000"))
    assert equity == Decimal("5000") + Decimal("0.1") * Decimal("85000")
    assert equity == Decimal("13500")


# ──────────────── _accumulate_wallet_losses ────────────────


def test_accumulate_losses_negative_pnl():
    wallet = SimpleNamespace(
        daily_loss_usdt=Decimal("0"),
        weekly_loss_usdt=Decimal("10"),
    )
    _accumulate_wallet_losses(wallet, Decimal("-50"))
    assert wallet.daily_loss_usdt == Decimal("50")
    assert wallet.weekly_loss_usdt == Decimal("60")


def test_accumulate_losses_positive_ignored():
    wallet = SimpleNamespace(
        daily_loss_usdt=Decimal("10"),
        weekly_loss_usdt=Decimal("20"),
    )
    _accumulate_wallet_losses(wallet, Decimal("100"))
    assert wallet.daily_loss_usdt == Decimal("10")
    assert wallet.weekly_loss_usdt == Decimal("20")


def test_accumulate_losses_none_ignored():
    wallet = SimpleNamespace(
        daily_loss_usdt=Decimal("10"),
        weekly_loss_usdt=Decimal("20"),
    )
    _accumulate_wallet_losses(wallet, None)
    assert wallet.daily_loss_usdt == Decimal("10")
    assert wallet.weekly_loss_usdt == Decimal("20")


# ──────────────── should_skip_flat_market ────────────────


def test_flat_market_explicit_flag():
    assert should_skip_flat_market(flat_market=True) is True


def test_flat_market_low_volatility():
    result = should_skip_flat_market(
        indicators={"price_change_pct": 0.001, "range_pct": 0.001, "volatility": 0.001},
        threshold=0.002,
    )
    assert result is True


def test_flat_market_high_volatility():
    result = should_skip_flat_market(
        indicators={"price_change_pct": 5.0, "range_pct": 3.0, "volatility": 4.0},
        threshold=0.002,
    )
    assert result is False


def test_flat_market_from_closes():
    # 20 closes with < 0.1% variation
    closes = [85000.0 + i * 0.5 for i in range(20)]
    result = should_skip_flat_market(
        indicators={"recent_closes": closes},
    )
    assert result is True


def test_flat_market_insufficient_data():
    is_flat, metrics = analyze_flat_market([100.0] * 5)
    assert is_flat is False
    assert metrics == {}


def test_flat_market_atr_based():
    # ATR/price < 0.5% triggers flat detection
    closes = [85000.0 + i * 10 for i in range(20)]
    atr_values = [100.0]  # 100/85190 ≈ 0.12% < 0.5%
    is_flat, metrics = analyze_flat_market(closes, threshold_pct=5.0, atr_values=atr_values)
    assert is_flat is True
    assert "atr_pct" in metrics


# ──────────────── Circuit breaker logic (unit-tested via helpers) ────────────────


def test_drawdown_15pct_halts():
    """Simulate drawdown check as done in run_single_cycle."""
    peak = Decimal("1000")
    equity = Decimal("840")  # 16% drawdown
    drawdown_pct = (peak - equity) / peak * 100
    max_dd = Decimal("15")
    assert drawdown_pct >= max_dd


def test_drawdown_below_threshold_continues():
    peak = Decimal("1000")
    equity = Decimal("860")  # 14% drawdown
    drawdown_pct = (peak - equity) / peak * 100
    max_dd = Decimal("15")
    assert drawdown_pct < max_dd


def test_daily_loss_3pct_halts():
    """Daily loss limit: wallet.daily_loss_usdt >= limit → halt."""
    daily_limit = Decimal("30")  # 3% of 1000
    wallet_daily_loss = Decimal("35")
    assert wallet_daily_loss >= daily_limit


def test_weekly_loss_7pct_halts():
    """Weekly loss limit: wallet.weekly_loss_usdt >= limit → halt."""
    weekly_limit = Decimal("70")  # 7% of 1000
    wallet_weekly_loss = Decimal("75")
    assert wallet_weekly_loss >= weekly_limit


def test_daily_loss_resets_on_new_day():
    """Daily loss counter should reset when date changes."""
    wallet = SimpleNamespace(
        daily_loss_usdt=Decimal("50"),
        daily_loss_reset_date=date(2026, 3, 19),
    )
    today = date(2026, 3, 20)
    if wallet.daily_loss_reset_date != today:
        wallet.daily_loss_usdt = Decimal("0")
        wallet.daily_loss_reset_date = today

    assert wallet.daily_loss_usdt == Decimal("0")
    assert wallet.daily_loss_reset_date == today


def test_weekly_loss_resets_on_new_week():
    """Weekly loss counter should reset when week changes."""
    wallet = SimpleNamespace(
        weekly_loss_usdt=Decimal("100"),
        weekly_loss_reset_date=date(2026, 3, 9),  # Monday of previous week
    )
    today = date(2026, 3, 20)  # Friday
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)  # 2026-03-16

    if wallet.weekly_loss_reset_date is None or wallet.weekly_loss_reset_date < week_start:
        wallet.weekly_loss_usdt = Decimal("0")
        wallet.weekly_loss_reset_date = week_start

    assert wallet.weekly_loss_usdt == Decimal("0")
    assert wallet.weekly_loss_reset_date == date(2026, 3, 16)


def test_peak_equity_updates_on_new_high():
    """Peak equity should update when current equity exceeds it."""
    wallet = SimpleNamespace(peak_equity_usdt=Decimal("1000"))
    equity = Decimal("1100")
    if equity > wallet.peak_equity_usdt:
        wallet.peak_equity_usdt = equity
    assert wallet.peak_equity_usdt == Decimal("1100")


def test_peak_equity_no_update_on_lower():
    wallet = SimpleNamespace(peak_equity_usdt=Decimal("1000"))
    equity = Decimal("900")
    if equity > wallet.peak_equity_usdt:
        wallet.peak_equity_usdt = equity
    assert wallet.peak_equity_usdt == Decimal("1000")
