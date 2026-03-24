"""WhatsApp trade notifications via Twilio."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_twilio_client = None
_initialized = False


def _get_twilio_client():
    """Lazily initialize the Twilio client."""
    global _twilio_client, _initialized
    if _initialized:
        return _twilio_client
    _initialized = True

    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.info("Twilio credentials not configured — WhatsApp notifications disabled")
        return None

    try:
        from twilio.rest import Client
        _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        logger.info("Twilio WhatsApp notifications enabled")
    except ImportError:
        logger.warning("twilio package not installed — WhatsApp notifications disabled")
    except Exception:
        logger.exception("Failed to initialize Twilio client")

    return _twilio_client


def _fmt(value: float | Decimal | None, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{decimals}f}"


def _build_trade_message(event: dict[str, Any]) -> str:
    """Format a trade_executed event into a readable WhatsApp message."""
    action = event.get("action", "?")
    symbol = event.get("symbol", "?")
    price = event.get("price")
    fee = event.get("fee")
    pnl = event.get("pnl")
    reason = event.get("reason", "")
    source = event.get("decision_source", "")
    strategy_name = event.get("strategy_name", "")
    cost_usdt = event.get("cost_usdt")
    wallet_before = event.get("wallet_balance_before")

    emoji = "🟢" if action == "BUY" else "🔴"
    header = f"{emoji} *{action} {symbol}*"

    # Calculate budget allocation percentage
    allocation_pct = None
    if cost_usdt and wallet_before and wallet_before > 0:
        allocation_pct = (cost_usdt / wallet_before) * 100

    lines = [
        header,
        "",
        f"*Price:* ${_fmt(price)}",
        f"*Allocation:* {_fmt(allocation_pct, 1)}%" if allocation_pct is not None else f"*Cost:* ${_fmt(cost_usdt)}",
        f"*Fee:* ${_fmt(fee, 4)}",
    ]

    if pnl is not None:
        pnl_emoji = "✅" if pnl >= 0 else "❌"
        lines.append(f"*P&L:* {pnl_emoji} ${_fmt(pnl, 4)}")

    if source:
        lines.append(f"*Source:* {source}")

    if reason:
        # Truncate long AI reasoning for WhatsApp
        short_reason = reason if len(str(reason)) <= 200 else str(reason)[:197] + "..."
        lines.append(f"*Reason:* {short_reason}")

    if strategy_name:
        lines.append(f"\n_Strategy: {strategy_name}_")

    return "\n".join(lines)


async def send_trade_notification(event: dict[str, Any]) -> None:
    """Send a WhatsApp message for a trade event. Runs in background, never raises."""
    settings = get_settings()
    if not settings.twilio_whatsapp_to:
        return

    try:
        client = await asyncio.get_event_loop().run_in_executor(None, _get_twilio_client)
        if client is None:
            return

        message_body = _build_trade_message(event)

        # Send to each recipient (supports multiple numbers / group)
        for recipient in settings.twilio_whatsapp_to:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda to=recipient: client.messages.create(
                    body=message_body,
                    from_=f"whatsapp:{settings.twilio_whatsapp_from}",
                    to=f"whatsapp:{to}",
                ),
            )

        logger.info("WhatsApp notification sent for %s %s", event.get("action"), event.get("symbol"))

    except Exception:
        logger.exception("Failed to send WhatsApp notification")
