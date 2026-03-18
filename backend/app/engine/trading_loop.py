"""Main trading loop — one asyncio.Task per strategy."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.engine.executor import execute_buy, execute_sell
from app.engine.wallet_manager import get_or_create_wallet, get_position
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.strategies.registry import get_strategy_class

logger = logging.getLogger(__name__)


async def run_single_cycle(
    strategy_id: str,
    symbol: str = "BTCUSDT",
    interval: str = "5m",
) -> dict | None:
    """Execute one decision cycle for a strategy. Returns trade info or None."""
    store = DataStore.get_instance()
    closes = store.get_closes(symbol, interval)

    if len(closes) < 50:
        logger.warning("Not enough candle data (%d) for strategy %s", len(closes), strategy_id)
        return None

    async with SessionLocal() as session:
        # Load strategy
        result = await session.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        if strategy is None or not strategy.is_active:
            return None

        # Get strategy config
        config = strategy.config_json or {}
        strategy_type = config.get("strategy_type", "sma_crossover")

        # Compute indicators
        indicators = compute_indicators(closes, config)

        # Get wallet and position
        wallet = await get_or_create_wallet(
            session, strategy_id, Decimal(str(config.get("initial_balance", 1000)))
        )
        position = await get_position(session, strategy_id, symbol)
        has_position = position is not None

        # Make decision
        strategy_impl = get_strategy_class(strategy_type)()
        signal = strategy_impl.decide(indicators, has_position, wallet.available_usdt)

        if signal is None:
            return None

        # Get current price
        current_price = store.get_latest_price(symbol)
        if current_price is None:
            logger.warning("No price available for %s", symbol)
            return None

        market_price = Decimal(str(current_price))

        # Execute
        if signal.action.value == "BUY":
            result = await execute_buy(
                session, strategy_id, wallet, symbol, market_price,
                signal.quantity_pct, reason=signal.reason,
            )
        else:
            result = await execute_sell(
                session, strategy_id, wallet, symbol, market_price,
                signal.quantity_pct, reason=signal.reason,
            )

        if result.success:
            logger.info(
                "Strategy %s executed %s %s @ %s",
                strategy_id, signal.action.value, symbol, result.trade.price,
            )
            await session.commit()
            return {
                "strategy_id": strategy_id,
                "action": signal.action.value,
                "symbol": symbol,
                "price": str(result.trade.price),
                "quantity": str(result.trade.quantity),
                "fee": str(result.trade.fee),
                "pnl": str(result.trade.pnl) if result.trade.pnl else None,
                "reason": signal.reason,
            }
        else:
            logger.warning("Execution failed for %s: %s", strategy_id, result.error)
            return None


async def take_equity_snapshot(strategy_id: str, symbol: str = "BTCUSDT") -> None:
    """Save current equity (cash + position value) as a snapshot."""
    store = DataStore.get_instance()
    price = store.get_latest_price(symbol)

    async with SessionLocal() as session:
        wallet = await get_or_create_wallet(session, strategy_id)
        position = await get_position(session, strategy_id, symbol)

        total = wallet.available_usdt
        if position and price:
            total += position.quantity * Decimal(str(price))

        snapshot = Snapshot(
            strategy_id=strategy_id,
            total_equity_usdt=total,
        )
        session.add(snapshot)
        await session.commit()


async def strategy_loop(strategy_id: str, interval_seconds: int = 300) -> None:
    """Continuous trading loop for a single strategy."""
    symbol = "BTCUSDT"
    cycle = 0

    while True:
        try:
            await run_single_cycle(strategy_id, symbol)
            cycle += 1

            # Snapshot every 5 cycles
            if cycle % 5 == 0:
                await take_equity_snapshot(strategy_id, symbol)

        except Exception:
            logger.exception("Error in strategy loop %s", strategy_id)

        await asyncio.sleep(interval_seconds)
