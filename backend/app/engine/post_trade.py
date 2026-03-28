"""Post-trade pipeline — handles notifications, broadcasts, streak updates, and equity tracking.

Extracted from inline code in trading_loop.py for reuse across all strategy types.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ws import ConnectionManager
from app.database import commit_with_write_lock
from app.engine.executor import ExecutionResult
from app.engine.position_sizer import streak_multiplier_for_losses
from app.engine.wallet_manager import get_position
from app.notifications.whatsapp import send_trade_notification

logger = logging.getLogger(__name__)


def update_strategy_streak(strategy: Any, pnl: Decimal | None) -> None:
    """Update consecutive loss tracking on strategy model."""
    if pnl is None:
        return

    if pnl < 0:
        strategy.consecutive_losses += 1
        strategy.max_consecutive_losses = max(
            strategy.max_consecutive_losses,
            strategy.consecutive_losses,
        )
    elif pnl > 0:
        strategy.consecutive_losses = 0

    strategy.streak_size_multiplier = streak_multiplier_for_losses(
        strategy.consecutive_losses
    )


def accumulate_wallet_losses(wallet: Any, pnl: Decimal | None) -> None:
    """Track daily/weekly losses on the wallet for limit enforcement."""
    if pnl is None or pnl >= 0:
        return
    loss = abs(pnl)
    wallet.daily_loss_usdt = (wallet.daily_loss_usdt or Decimal("0")) + loss
    wallet.weekly_loss_usdt = (wallet.weekly_loss_usdt or Decimal("0")) + loss


def compute_equity(wallet: Any, position: Any, market_price: Decimal) -> Decimal:
    """Cash + mark-to-market position value."""
    equity = wallet.available_usdt
    if position is not None:
        equity += position.quantity * market_price
    return equity


async def broadcast_trade_event(
    manager: ConnectionManager,
    *,
    strategy_id: str,
    action: str,
    symbol: str,
    trade: Any,
    reason: str,
    decision_source: str,
    strategy_name: str | None = None,
) -> None:
    """Broadcast trade execution event via WebSocket and send WhatsApp notification."""
    event = {
        "type": "trade_executed",
        "strategy_id": strategy_id,
        "action": action,
        "symbol": symbol,
        "price": float(trade.price),
        "quantity": float(trade.quantity),
        "fee": float(trade.fee),
        "pnl": float(trade.pnl) if trade.pnl is not None else None,
        "reason": reason,
        "decision_source": decision_source,
        "cost_usdt": float(trade.cost_usdt) if trade.cost_usdt else None,
        "wallet_balance_before": (
            float(trade.wallet_balance_before) if trade.wallet_balance_before else None
        ),
        "strategy_name": strategy_name,
    }
    await manager.broadcast(event)
    asyncio.create_task(send_trade_notification(event))


async def broadcast_position_change(
    manager: ConnectionManager,
    *,
    strategy_id: str,
    symbol: str,
    position: Any,
    available_usdt: Decimal,
) -> None:
    """Broadcast position change event via WebSocket."""
    await manager.broadcast(
        {
            "type": "position_changed",
            "strategy_id": strategy_id,
            "symbol": symbol,
            "has_position": position is not None,
            "quantity": float(position.quantity) if position else 0.0,
            "entry_price": float(position.entry_price) if position else None,
            "available_usdt": float(available_usdt),
        }
    )


async def handle_post_trade(
    session: Any,
    manager: ConnectionManager,
    *,
    result: ExecutionResult,
    strategy: Any,
    strategy_id: str,
    wallet: Any,
    symbol: str,
    market_price: Decimal,
    action: str,
    reason: str,
    decision_source: str,
    is_sell: bool = False,
    exit_decision: Any = None,
) -> None:
    """Full post-trade processing: streaks, wallet losses, commit, broadcast.

    Handles both BUY and SELL sides.
    """
    config = strategy.config_json or {}

    if is_sell:
        update_strategy_streak(strategy, result.trade.pnl)
        accumulate_wallet_losses(wallet, result.trade.pnl)
        await _record_scanner_perf_stats(session, strategy_id, symbol, result)

        # Track stop-loss exits for re-entry cooldown
        is_stop_loss = (
            "stop-loss" in (reason or "").lower()
            or "stop_loss" in (reason or "").lower()
            or (exit_decision is not None and getattr(exit_decision, "exit_type", None) == "stop_loss")
        )
        if is_stop_loss:
            strategy.last_stop_loss_symbol = symbol
            strategy.last_stop_loss_at = datetime.now(timezone.utc)

        # Handle exit-specific position updates
        if exit_decision is not None:
            refreshed_position = await get_position(session, strategy_id, symbol)
            if refreshed_position is not None:
                if getattr(exit_decision, "consume_take_profit", False):
                    refreshed_position.take_profit_price = None
                if getattr(exit_decision, "updated_trailing_stop_price", None) is not None:
                    refreshed_position.trailing_stop_price = (
                        exit_decision.updated_trailing_stop_price
                    )
    else:
        # BUY side — set stop-loss on new position
        from app.config import get_settings
        settings = get_settings()
        refreshed_position = await get_position(session, strategy_id, symbol)
        if refreshed_position is not None:
            # For hybrid, stop-loss comes from sizing; for rule-based, from config
            if not getattr(refreshed_position, "stop_loss_price", None):
                sl_pct = Decimal(
                    str(strategy.stop_loss_pct or settings.default_stop_loss_pct)
                ) / 100
                refreshed_position.stop_loss_price = (
                    refreshed_position.entry_price * (1 - sl_pct)
                ).quantize(Decimal("0.00000001"))

    await commit_with_write_lock(session)

    # Refresh position after commit
    refreshed_position = await get_position(session, strategy_id, symbol)

    # Update peak equity
    new_equity = compute_equity(wallet, refreshed_position, market_price)
    if new_equity > wallet.peak_equity_usdt:
        wallet.peak_equity_usdt = new_equity
        await commit_with_write_lock(session)

    # Broadcast events
    await broadcast_trade_event(
        manager,
        strategy_id=strategy_id,
        action=action,
        symbol=symbol,
        trade=result.trade,
        reason=reason,
        decision_source=decision_source,
        strategy_name=strategy.name,
    )
    await broadcast_position_change(
        manager,
        strategy_id=strategy_id,
        symbol=symbol,
        position=refreshed_position,
        available_usdt=wallet.available_usdt,
    )


async def _record_scanner_perf_stats(
    session: Any,
    strategy_id: str,
    symbol: str,
    result: ExecutionResult,
) -> None:
    """Upsert scanner perf stats after a closed trade."""
    try:
        from app.models.position import Position
        from app.models.scanner_perf_stats import ScannerPerfStats

        # Look up the position to get scanner context
        pos = (
            await session.execute(
                select(Position).where(
                    Position.strategy_id == strategy_id,
                    Position.symbol == symbol,
                )
            )
        ).scalars().first()

        if pos is None:
            return
        family = getattr(pos, "entry_scanner_family", None)
        regime = getattr(pos, "entry_scanner_regime", None)
        if not family or not regime:
            return  # no scanner context on this position

        side = pos.side.value if hasattr(pos.side, "value") else str(pos.side)
        pnl = result.trade.pnl
        is_win = pnl is not None and pnl > 0

        # Check for existing row
        existing = (
            await session.execute(
                select(ScannerPerfStats).where(
                    ScannerPerfStats.symbol == symbol,
                    ScannerPerfStats.setup_family == family,
                    ScannerPerfStats.detailed_regime == regime,
                    ScannerPerfStats.side == side,
                )
            )
        ).scalars().first()

        now = datetime.now(timezone.utc)
        pnl_pct = float(pnl / pos.entry_price * 100) if pnl is not None and pos.entry_price else 0.0
        hold_hours = (now - pos.opened_at).total_seconds() / 3600 if pos.opened_at else 0.0

        if existing:
            n = existing.total_trades
            existing.total_trades = n + 1
            existing.wins = existing.wins + (1 if is_win else 0)
            existing.losses = existing.losses + (0 if is_win else 1)
            existing.avg_pnl_pct = (existing.avg_pnl_pct * n + pnl_pct) / (n + 1)
            existing.avg_hold_hours = (existing.avg_hold_hours * n + hold_hours) / (n + 1)
            existing.last_updated = now
        else:
            from uuid import uuid4
            session.add(ScannerPerfStats(
                id=str(uuid4()),
                symbol=symbol,
                setup_family=family,
                detailed_regime=regime,
                side=side,
                total_trades=1,
                wins=1 if is_win else 0,
                losses=0 if is_win else 1,
                avg_pnl_pct=pnl_pct,
                avg_hold_hours=hold_hours,
                last_updated=now,
            ))
    except Exception:
        logger.warning("Failed to record scanner perf stats for %s", symbol, exc_info=True)
