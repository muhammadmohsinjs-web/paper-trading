"""Order execution engine — the core of the paper trading simulator.

Flow: market_price → slippage → fee → wallet update → trade record → P&L
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.fee_model import SPOT_FEE_RATE, calculate_fee
from app.engine.slippage import apply_slippage
from app.engine.wallet_manager import (
    close_position,
    credit_wallet,
    debit_wallet,
    get_position,
    open_position,
)
from app.models.enums import TradeSide
from app.models.trade import Trade
from app.models.wallet import Wallet


@dataclass
class TradeSignal:
    action: TradeSide
    symbol: str
    quantity_pct: Decimal = Decimal("1.0")  # fraction of available balance / position
    reason: str = ""


@dataclass
class ExecutionResult:
    trade: Trade
    success: bool = True
    error: str | None = None


async def execute_buy(
    session: AsyncSession,
    strategy_id: str,
    wallet: Wallet,
    symbol: str,
    market_price: Decimal,
    quantity_pct: Decimal = Decimal("1.0"),
    fee_rate: Decimal = SPOT_FEE_RATE,
    reason: str = "",
    *,
    strategy_name: str | None = None,
    strategy_type: str | None = None,
    decision_source: str | None = None,
    indicator_snapshot: dict | None = None,
    composite_score: Decimal | None = None,
    composite_confidence: Decimal | None = None,
) -> ExecutionResult:
    """Execute a BUY order: calculate cost, apply slippage/fees, debit wallet, open position."""
    wallet_balance_before = wallet.available_usdt

    # Determine how much USDT to spend
    spend_usdt = (wallet.available_usdt * quantity_pct).quantize(Decimal("0.00000001"))
    if spend_usdt <= Decimal("0"):
        return ExecutionResult(trade=None, success=False, error="Nothing to spend")  # type: ignore[arg-type]

    # Apply slippage
    exec_price, slippage_amt = apply_slippage(market_price, spend_usdt, TradeSide.BUY)

    # Calculate quantity we can buy at execution price
    fee = calculate_fee(spend_usdt, fee_rate)
    net_spend = spend_usdt - fee
    quantity = (net_spend / exec_price).quantize(Decimal("0.00000001"))

    if quantity <= Decimal("0"):
        return ExecutionResult(trade=None, success=False, error="Quantity too small")  # type: ignore[arg-type]

    # Debit wallet
    await debit_wallet(session, wallet, spend_usdt)

    # Open or add to position
    existing = await get_position(session, strategy_id, symbol)
    if existing:
        # Average into existing position
        total_qty = existing.quantity + quantity
        existing.entry_price = (
            (existing.entry_price * existing.quantity + exec_price * quantity) / total_qty
        ).quantize(Decimal("0.00000001"))
        existing.quantity = total_qty
        existing.entry_fee = existing.entry_fee + fee
        await session.flush()
    else:
        await open_position(session, strategy_id, symbol, quantity, exec_price, fee)

    wallet_balance_after = wallet.available_usdt

    # Record trade
    trade = Trade(
        id=str(uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=TradeSide.BUY,
        quantity=quantity,
        price=exec_price,
        market_price=market_price,
        fee=fee,
        slippage=slippage_amt,
        pnl=None,
        pnl_pct=None,
        ai_reasoning=reason or None,
        cost_usdt=spend_usdt,
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        decision_source=decision_source,
        indicator_snapshot=indicator_snapshot,
        composite_score=composite_score,
        composite_confidence=composite_confidence,
        wallet_balance_before=wallet_balance_before,
        wallet_balance_after=wallet_balance_after,
    )
    session.add(trade)
    await session.flush()

    return ExecutionResult(trade=trade)


async def execute_sell(
    session: AsyncSession,
    strategy_id: str,
    wallet: Wallet,
    symbol: str,
    market_price: Decimal,
    quantity_pct: Decimal = Decimal("1.0"),
    fee_rate: Decimal = SPOT_FEE_RATE,
    reason: str = "",
    *,
    strategy_name: str | None = None,
    strategy_type: str | None = None,
    decision_source: str | None = None,
    indicator_snapshot: dict | None = None,
    composite_score: Decimal | None = None,
    composite_confidence: Decimal | None = None,
) -> ExecutionResult:
    """Execute a SELL order: close position, calculate P&L, credit wallet."""
    wallet_balance_before = wallet.available_usdt

    position = await get_position(session, strategy_id, symbol)
    if position is None:
        return ExecutionResult(trade=None, success=False, error="No position to sell")  # type: ignore[arg-type]

    # Determine quantity to sell
    sell_qty = (position.quantity * quantity_pct).quantize(Decimal("0.00000001"))
    if sell_qty <= Decimal("0"):
        return ExecutionResult(trade=None, success=False, error="Quantity too small")  # type: ignore[arg-type]

    notional = sell_qty * market_price
    exec_price, slippage_amt = apply_slippage(market_price, notional, TradeSide.SELL)

    # Proceeds after fee
    gross_proceeds = sell_qty * exec_price
    fee = calculate_fee(gross_proceeds, fee_rate)
    net_proceeds = gross_proceeds - fee

    # P&L calculation
    cost_basis = sell_qty * position.entry_price
    # Proportional entry fee
    entry_fee_portion = (position.entry_fee * sell_qty / position.quantity).quantize(
        Decimal("0.00000001")
    )
    pnl = net_proceeds - cost_basis - entry_fee_portion
    pnl_pct = (pnl / cost_basis * Decimal("100")).quantize(Decimal("0.000001")) if cost_basis else Decimal("0")

    # Credit wallet
    await credit_wallet(session, wallet, net_proceeds)

    # Update or close position
    remaining = position.quantity - sell_qty
    if remaining <= Decimal("0.00000001"):
        await close_position(session, position)
    else:
        position.quantity = remaining
        position.entry_fee = position.entry_fee - entry_fee_portion
        await session.flush()

    wallet_balance_after = wallet.available_usdt

    # Record trade
    trade = Trade(
        id=str(uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=TradeSide.SELL,
        quantity=sell_qty,
        price=exec_price,
        market_price=market_price,
        fee=fee,
        slippage=slippage_amt,
        pnl=pnl,
        pnl_pct=pnl_pct,
        ai_reasoning=reason or None,
        cost_usdt=net_proceeds,
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        decision_source=decision_source,
        indicator_snapshot=indicator_snapshot,
        composite_score=composite_score,
        composite_confidence=composite_confidence,
        wallet_balance_before=wallet_balance_before,
        wallet_balance_after=wallet_balance_after,
    )
    session.add(trade)
    await session.flush()

    return ExecutionResult(trade=trade)
