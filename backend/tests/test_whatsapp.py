"""Tests for WhatsApp trade notification formatting and sending."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.notifications.whatsapp import (
    _build_trade_message,
    _fmt,
    send_trade_notification,
)


# ---------------------------------------------------------------------------
# _fmt helper
# ---------------------------------------------------------------------------

class TestFmt:
    def test_none_returns_dash(self):
        assert _fmt(None) == "—"

    def test_float_default_decimals(self):
        assert _fmt(67432.1) == "67,432.10"

    def test_custom_decimals(self):
        assert _fmt(0.00148200, 8) == "0.00148200"

    def test_zero(self):
        assert _fmt(0) == "0.00"


# ---------------------------------------------------------------------------
# _build_trade_message
# ---------------------------------------------------------------------------

def _make_event(**overrides) -> dict:
    base = {
        "type": "trade_executed",
        "strategy_id": "abc-123",
        "action": "BUY",
        "symbol": "BTCUSDT",
        "price": 67432.15,
        "quantity": 0.00148200,
        "fee": 0.0999,
        "pnl": None,
        "reason": "Strong bullish momentum",
        "decision_source": "hybrid_entry",
        "cost_usdt": 100.0,
        "wallet_balance_before": 1000.0,
        "strategy_name": "BTC Scalper",
    }
    base.update(overrides)
    return base


class TestBuildTradeMessage:
    def test_buy_message_contains_key_fields(self):
        msg = _build_trade_message(_make_event())
        assert "BUY BTCUSDT" in msg
        assert "67,432.15" in msg
        assert "Allocation:* 10.0%" in msg
        assert "hybrid_entry" in msg
        assert "BTC Scalper" in msg

    def test_sell_message_with_pnl(self):
        msg = _build_trade_message(_make_event(
            action="SELL",
            pnl=25.50,
            decision_source="hybrid_exit",
        ))
        assert "SELL BTCUSDT" in msg
        assert "P&L:" in msg
        assert "25.5000" in msg
        assert "✅" in msg

    def test_sell_message_negative_pnl(self):
        msg = _build_trade_message(_make_event(action="SELL", pnl=-10.0))
        assert "❌" in msg

    def test_allocation_percentage_calculation(self):
        # 250 / 1000 = 25%
        msg = _build_trade_message(_make_event(cost_usdt=250.0, wallet_balance_before=1000.0))
        assert "25.0%" in msg

    def test_fallback_to_cost_when_no_wallet_balance(self):
        msg = _build_trade_message(_make_event(wallet_balance_before=None))
        assert "Cost:" in msg
        assert "Allocation:" not in msg

    def test_fallback_to_cost_when_zero_wallet_balance(self):
        msg = _build_trade_message(_make_event(wallet_balance_before=0))
        assert "Cost:" in msg

    def test_strategy_name_shown(self):
        msg = _build_trade_message(_make_event(strategy_name="My Alpha Strategy"))
        assert "My Alpha Strategy" in msg

    def test_no_strategy_name_omits_line(self):
        msg = _build_trade_message(_make_event(strategy_name=""))
        assert "Strategy:" not in msg

    def test_long_reason_truncated(self):
        long_reason = "x" * 300
        msg = _build_trade_message(_make_event(reason=long_reason))
        assert "..." in msg
        # Should be capped around 200 chars
        reason_line = [l for l in msg.split("\n") if "Reason:" in l][0]
        assert len(reason_line) < 220

    def test_buy_emoji(self):
        msg = _build_trade_message(_make_event(action="BUY"))
        assert "🟢" in msg

    def test_sell_emoji(self):
        msg = _build_trade_message(_make_event(action="SELL", pnl=0))
        assert "🔴" in msg

    def test_no_source_omits_line(self):
        msg = _build_trade_message(_make_event(decision_source=""))
        assert "Source:" not in msg

    def test_no_reason_omits_line(self):
        msg = _build_trade_message(_make_event(reason=""))
        assert "Reason:" not in msg


# ---------------------------------------------------------------------------
# send_trade_notification
# ---------------------------------------------------------------------------

class TestSendTradeNotification:
    @pytest.mark.asyncio
    async def test_skips_when_no_recipients(self):
        """Should return immediately when no TWILIO_WHATSAPP_TO configured."""
        with patch("app.notifications.whatsapp.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(twilio_whatsapp_to=[])
            # Should not raise
            await send_trade_notification(_make_event())

    @pytest.mark.asyncio
    async def test_sends_to_all_recipients(self):
        """Should call Twilio create for each recipient."""
        mock_client = MagicMock()
        mock_create = MagicMock()
        mock_client.messages.create = mock_create

        with patch("app.notifications.whatsapp.get_settings") as mock_settings, \
             patch("app.notifications.whatsapp._get_twilio_client", return_value=mock_client):
            mock_settings.return_value = MagicMock(
                twilio_whatsapp_to=["+1111111111", "+2222222222"],
                twilio_whatsapp_from="+14155238886",
            )
            await send_trade_notification(_make_event())

        assert mock_create.call_count == 2
        # Verify both recipients received messages
        call_tos = [call.kwargs["to"] for call in mock_create.call_args_list]
        assert "whatsapp:+1111111111" in call_tos
        assert "whatsapp:+2222222222" in call_tos

    @pytest.mark.asyncio
    async def test_does_not_raise_on_twilio_error(self):
        """Notification failures should be swallowed, not crash the trading loop."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Twilio down")

        with patch("app.notifications.whatsapp.get_settings") as mock_settings, \
             patch("app.notifications.whatsapp._get_twilio_client", return_value=mock_client):
            mock_settings.return_value = MagicMock(
                twilio_whatsapp_to=["+1111111111"],
                twilio_whatsapp_from="+14155238886",
            )
            # Should not raise
            await send_trade_notification(_make_event())

    @pytest.mark.asyncio
    async def test_skips_when_client_is_none(self):
        """Should gracefully skip when Twilio client fails to initialize."""
        with patch("app.notifications.whatsapp.get_settings") as mock_settings, \
             patch("app.notifications.whatsapp._get_twilio_client", return_value=None):
            mock_settings.return_value = MagicMock(
                twilio_whatsapp_to=["+1111111111"],
            )
            await send_trade_notification(_make_event())
