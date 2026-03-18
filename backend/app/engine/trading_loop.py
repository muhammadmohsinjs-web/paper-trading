"""Main trading loop — one asyncio.Task per strategy."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.api.ws import ConnectionManager
from app.config import get_settings
from app.database import SessionLocal
from app.engine.executor import execute_buy, execute_sell
from app.engine.ai_runtime import (
    AIDecisionResult,
    AIUsage,
    build_ai_context,
    analyze_flat_market,
    evaluate_ai_decision,
    normalize_ai_strategy_key,
)
from app.engine.wallet_manager import get_or_create_wallet, get_position
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.strategies.registry import get_strategy_class

logger = logging.getLogger(__name__)
settings = get_settings()


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _strategy_last_ai_at(strategy: Any) -> datetime | None:
    return _as_aware(
        getattr(strategy, "ai_last_decision_at", None)
        or getattr(strategy, "last_ai_decision_at", None)
        or getattr(strategy, "last_ai_call_at", None)
    )


def _normalize_ai_counters(strategy: Strategy) -> dict[str, Any]:
    config = strategy.config_json or {}
    cooldown_seconds = int(
        strategy.ai_cooldown_seconds
        or config.get("ai_cooldown_seconds")
        or settings.ai_min_cooldown_seconds
    )
    return {
        "ai_enabled": bool(strategy.ai_enabled or config.get("ai_enabled", False)),
        "ai_strategy_key": normalize_ai_strategy_key(
            strategy.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type"),
        ),
        "ai_model": str(strategy.ai_model or config.get("ai_model") or settings.anthropic_model),
        "ai_cooldown_seconds": max(cooldown_seconds, settings.ai_min_cooldown_seconds),
        "ai_max_tokens": int(strategy.ai_max_tokens or config.get("ai_max_tokens") or settings.ai_max_tokens),
        "ai_temperature": Decimal(
            str(strategy.ai_temperature if strategy.ai_temperature is not None else config.get("ai_temperature", settings.ai_temperature))
        ),
        "flat_market_threshold_pct": float(
            config.get("flat_market_threshold_pct", settings.ai_flat_market_threshold_pct)
        ),
    }


def _cooldown_remaining(strategy: Strategy, cooldown_seconds: int) -> int:
    last_decision_at = _strategy_last_ai_at(strategy)
    if last_decision_at is None:
        return 0

    elapsed = (datetime.now(timezone.utc) - last_decision_at).total_seconds()
    remaining = int(cooldown_seconds - elapsed)
    return max(0, remaining)


def should_skip_ai_call(
    strategy: Any,
    cooldown_seconds: int | None = None,
    now: datetime | None = None,
    **_: Any,
) -> bool:
    config = getattr(strategy, "config_json", {}) or {}
    cooldown = int(
        cooldown_seconds
        or config.get("ai_cooldown_seconds")
        or getattr(strategy, "ai_cooldown_seconds", 0)
        or settings.ai_min_cooldown_seconds
    )
    last_decision_at = _strategy_last_ai_at(strategy)
    if last_decision_at is None:
        return False

    now_aware = _as_aware(now) or datetime.now(timezone.utc)
    return (now_aware - last_decision_at).total_seconds() < cooldown


def should_skip_flat_market(
    market_context: dict[str, Any] | None = None,
    indicators: dict[str, Any] | None = None,
    threshold: float | None = None,
    flat_market: bool | None = None,
    is_flat_market: bool | None = None,
    market_is_flat: bool | None = None,
    flat_market_threshold: float | None = None,
    **_: Any,
) -> bool:
    if any(flag is True for flag in (flat_market, is_flat_market, market_is_flat)):
        return True

    context = market_context or indicators or {}
    threshold_value = threshold if threshold is not None else flat_market_threshold
    if threshold_value is None:
        threshold_value = settings.ai_flat_market_threshold_pct / 100

    numeric_signals = [
        abs(float(context.get("price_change_pct", 0.0) or 0.0)),
        abs(float(context.get("range_pct", 0.0) or 0.0)),
        abs(float(context.get("volatility", 0.0) or 0.0)),
    ]
    if any(numeric_signals):
        return max(numeric_signals) <= float(threshold_value)

    closes = context.get("recent_closes") or context.get("closes") or []
    if closes:
        is_flat, _ = analyze_flat_market([float(value) for value in closes])
        return is_flat
    return False


def _serialize_usage(usage: AIUsage | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "model": usage.model,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "estimated_cost_usdt": float(usage.estimated_cost_usdt),
    }


def _serialize_signal_result(signal: dict[str, Any] | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "action": signal["action"],
        "symbol": signal["symbol"],
        "quantity_pct": float(signal["quantity_pct"]),
        "reason": signal["reason"],
    }


def _touch_ai_metrics(strategy: Strategy, decision: AIDecisionResult) -> None:
    if decision.usage is None:
        return

    usage = decision.usage
    strategy.ai_last_decision_at = datetime.now(timezone.utc)
    strategy.ai_last_decision_status = decision.status
    strategy.ai_last_reasoning = decision.reason or decision.raw_response
    strategy.ai_last_model = usage.model
    strategy.ai_last_prompt_tokens = usage.prompt_tokens
    strategy.ai_last_completion_tokens = usage.completion_tokens
    strategy.ai_last_total_tokens = usage.total_tokens
    strategy.ai_last_cost_usdt = usage.estimated_cost_usdt
    strategy.ai_total_calls += 1
    strategy.ai_total_prompt_tokens += usage.prompt_tokens
    strategy.ai_total_completion_tokens += usage.completion_tokens
    strategy.ai_total_tokens += usage.total_tokens
    strategy.ai_total_cost_usdt += usage.estimated_cost_usdt


async def run_single_cycle(
    strategy_id: str,
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    force: bool = False,
) -> dict[str, Any]:
    """Execute one decision cycle for a strategy."""
    store = DataStore.get_instance()
    manager = ConnectionManager.get_instance()
    candles = store.get_candles(symbol, interval)
    closes = [candle.close for candle in candles]

    if len(closes) < 50:
        logger.warning("Not enough candle data (%d) for strategy %s", len(closes), strategy_id)
        return {
            "status": "skipped",
            "reason": "Not enough candle data",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "market_data",
        }

    async with SessionLocal() as session:
        # Load strategy
        result = await session.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        if strategy is None or not strategy.is_active:
            return {
                "status": "skipped",
                "reason": "Strategy not found or inactive",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "strategy",
            }

        # Get strategy config
        config = strategy.config_json or {}
        strategy_type = config.get("strategy_type", "sma_crossover")
        ai_config = _normalize_ai_counters(strategy)

        # Compute indicators
        indicators = compute_indicators(closes, config)

        # Get wallet and position
        wallet = await get_or_create_wallet(
            session, strategy_id, Decimal(str(config.get("initial_balance", 1000)))
        )
        position = await get_position(session, strategy_id, symbol)
        has_position = position is not None

        current_price = store.get_latest_price(symbol)
        if current_price is None:
            logger.warning("No price available for %s", symbol)
            return {
                "status": "skipped",
                "reason": "No price data",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "market_data",
            }

        market_price = Decimal(str(current_price))

        if ai_config["ai_enabled"]:
            _, flat_metrics = analyze_flat_market(closes, ai_config["flat_market_threshold_pct"])
            cooldown_remaining = _cooldown_remaining(strategy, ai_config["ai_cooldown_seconds"])
            if cooldown_remaining > 0 and not force:
                return {
                    "status": "skipped",
                    "reason": "AI cooldown active",
                    "cooldown_remaining_seconds": cooldown_remaining,
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "cooldown",
                }

            ai_context = build_ai_context(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                symbol=symbol,
                interval=interval,
                closes=closes,
                highs=[candle.high for candle in candles],
                lows=[candle.low for candle in candles],
                volumes=[candle.volume for candle in candles],
                indicators=indicators,
                wallet_available_usdt=wallet.available_usdt,
                has_position=has_position,
                position_quantity=position.quantity if position else None,
                position_entry_price=position.entry_price if position else None,
                current_price=market_price,
                ai_strategy_key=ai_config["ai_strategy_key"],
                ai_model=ai_config["ai_model"],
                ai_cooldown_seconds=ai_config["ai_cooldown_seconds"],
                ai_max_tokens=ai_config["ai_max_tokens"],
                ai_temperature=ai_config["ai_temperature"],
                flat_market_metrics=flat_metrics or {"threshold_pct": ai_config["flat_market_threshold_pct"]},
            )

            ai_result = await evaluate_ai_decision(
                strategy_key=ai_config["ai_strategy_key"],
                context=ai_context,
                force=force,
            )

            if ai_result.status in {"skipped", "error"}:
                strategy.ai_last_decision_status = ai_result.status
                strategy.ai_last_reasoning = ai_result.reason or ai_result.error
                if ai_result.usage is not None:
                    _touch_ai_metrics(strategy, ai_result)
                await session.commit()
                return {
                    "status": "hold" if ai_result.status == "error" else ai_result.status,
                    "reason": ai_result.reason,
                    "error": ai_result.error,
                    "skip_reason": ai_result.skip_reason,
                    "usage": _serialize_usage(ai_result.usage),
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "ai",
                    "raw_response": ai_result.raw_response,
                }

            _touch_ai_metrics(strategy, ai_result)

            if ai_result.signal is None:
                await session.commit()
                return {
                    "status": "hold",
                    "reason": ai_result.reason or "AI returned HOLD",
                    "usage": _serialize_usage(ai_result.usage),
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "ai",
                    "raw_response": ai_result.raw_response,
                }

            signal = ai_result.signal
        else:
            # Make decision with the rule-based strategy
            strategy_impl = get_strategy_class(strategy_type)()
            signal = strategy_impl.decide(indicators, has_position, wallet.available_usdt)

        if signal is None:
            if ai_config["ai_enabled"]:
                await session.commit()
            return {
                "status": "hold",
                "reason": "No trade signal",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "ai" if ai_config["ai_enabled"] else "rule",
            }

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
            refreshed_position = await get_position(session, strategy_id, symbol)
            await manager.broadcast(
                {
                    "type": "trade_executed",
                    "strategy_id": strategy_id,
                    "action": signal.action.value,
                    "symbol": symbol,
                    "price": float(result.trade.price),
                    "quantity": float(result.trade.quantity),
                    "fee": float(result.trade.fee),
                    "pnl": float(result.trade.pnl) if result.trade.pnl is not None else None,
                    "reason": signal.reason,
                    "decision_source": "ai" if ai_config["ai_enabled"] else "rule",
                }
            )
            await manager.broadcast(
                {
                    "type": "position_changed",
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "has_position": refreshed_position is not None,
                    "quantity": float(refreshed_position.quantity) if refreshed_position else 0.0,
                    "entry_price": float(refreshed_position.entry_price) if refreshed_position else None,
                    "available_usdt": float(wallet.available_usdt),
                }
            )
            return {
                "status": "executed",
                "strategy_id": strategy_id,
                "action": signal.action.value,
                "symbol": symbol,
                "price": str(result.trade.price),
                "quantity": str(result.trade.quantity),
                "fee": str(result.trade.fee),
                "pnl": str(result.trade.pnl) if result.trade.pnl else None,
                "reason": signal.reason,
                "decision_source": "ai" if ai_config["ai_enabled"] else "rule",
                "usage": _serialize_usage(ai_result.usage) if ai_config["ai_enabled"] else None,
                "signal": _serialize_signal_result(
                    {
                        "action": signal.action.value,
                        "symbol": signal.symbol,
                        "quantity_pct": signal.quantity_pct,
                        "reason": signal.reason,
                    }
                ),
            }
        else:
            logger.warning("Execution failed for %s: %s", strategy_id, result.error)
            await session.rollback()
            return {
                "status": "failed",
                "reason": result.error,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "decision_source": "ai" if ai_config["ai_enabled"] else "rule",
            }


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
            result = await run_single_cycle(strategy_id, symbol)
            cycle += 1

            if result.get("status") == "executed":
                logger.info(
                    "Loop cycle %d executed for %s (%s)",
                    cycle,
                    strategy_id,
                    result.get("action"),
                )
            elif result.get("status") in {"skipped", "hold"}:
                logger.debug(
                    "Loop cycle %d for %s returned %s: %s",
                    cycle,
                    strategy_id,
                    result.get("status"),
                    result.get("reason"),
                )

            # Snapshot every 5 cycles
            if cycle % 5 == 0:
                await take_equity_snapshot(strategy_id, symbol)

        except Exception:
            logger.exception("Error in strategy loop %s", strategy_id)

        await asyncio.sleep(interval_seconds)
