"""Main trading loop — one asyncio.Task per strategy."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text

from app.api.ws import ConnectionManager
from app.config import default_ai_model_for_provider, get_settings, normalize_ai_provider
from app.database import SessionLocal
from app.engine.composite_scorer import compute_ai_vote, compute_composite_score
from app.engine.executor import execute_buy, execute_sell
from app.engine.ai_runtime import (
    AIDecisionResult,
    AIUsage,
    build_ai_context,
    analyze_flat_market,
    evaluate_ai_decision,
    normalize_ai_strategy_key,
)
from app.engine.exit_manager import evaluate_exit
from app.engine.position_sizer import calculate_position_size, streak_multiplier_for_losses
from app.engine.wallet_manager import get_or_create_wallet, get_position
from app.models.ai_call_log import AICallLog
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.strategies.registry import get_strategy_class

logger = logging.getLogger(__name__)
settings = get_settings()
_CYCLE_LOCK_TTL = timedelta(minutes=10)
_cycle_lock_table_ready = False
_cycle_lock_table_guard = asyncio.Lock()


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _ensure_cycle_lock_table() -> None:
    global _cycle_lock_table_ready

    if _cycle_lock_table_ready:
        return

    async with _cycle_lock_table_guard:
        if _cycle_lock_table_ready:
            return

        async with SessionLocal() as session:
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_cycle_locks (
                        strategy_id VARCHAR(36) PRIMARY KEY,
                        owner_id VARCHAR(36) NOT NULL,
                        acquired_at TEXT NOT NULL
                    )
                    """
                )
            )
            await session.commit()
        _cycle_lock_table_ready = True


async def _acquire_cycle_db_lock(strategy_id: str) -> str | None:
    await _ensure_cycle_lock_table()

    owner_id = str(uuid4())
    now = datetime.now(timezone.utc)
    stale_before = now - _CYCLE_LOCK_TTL

    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO strategy_cycle_locks (strategy_id, owner_id, acquired_at)
                VALUES (:strategy_id, :owner_id, :acquired_at)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    acquired_at = excluded.acquired_at
                WHERE strategy_cycle_locks.acquired_at < :stale_before
                """
            ),
            {
                "strategy_id": strategy_id,
                "owner_id": owner_id,
                "acquired_at": now.isoformat(),
                "stale_before": stale_before.isoformat(),
            },
        )
        await session.commit()

        current_owner = (
            await session.execute(
                text(
                    """
                    SELECT owner_id
                    FROM strategy_cycle_locks
                    WHERE strategy_id = :strategy_id
                    """
                ),
                {"strategy_id": strategy_id},
            )
        ).scalar_one_or_none()
    return owner_id if current_owner == owner_id else None


async def _release_cycle_db_lock(strategy_id: str, owner_id: str) -> None:
    await _ensure_cycle_lock_table()

    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                DELETE FROM strategy_cycle_locks
                WHERE strategy_id = :strategy_id
                  AND owner_id = :owner_id
                """
            ),
            {"strategy_id": strategy_id, "owner_id": owner_id},
        )
        await session.commit()


def _strategy_last_ai_at(strategy: Any) -> datetime | None:
    return _as_aware(
        getattr(strategy, "ai_last_decision_at", None)
        or getattr(strategy, "last_ai_decision_at", None)
        or getattr(strategy, "last_ai_call_at", None)
    )


def _normalize_ai_counters(strategy: Strategy) -> dict[str, Any]:
    config = strategy.config_json or {}
    ai_provider = normalize_ai_provider(
        strategy.ai_provider or config.get("ai_provider") or settings.ai_provider
    )
    cooldown_seconds = int(
        strategy.ai_cooldown_seconds
        or config.get("ai_cooldown_seconds")
        or settings.ai_min_cooldown_seconds
    )
    return {
        "ai_enabled": bool(strategy.ai_enabled or config.get("ai_enabled", False)),
        "ai_provider": ai_provider,
        "ai_strategy_key": normalize_ai_strategy_key(
            strategy.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type"),
        ),
        "ai_model": str(
            strategy.ai_model
            or config.get("ai_model")
            or default_ai_model_for_provider(ai_provider, settings)
        ),
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
        "provider": usage.provider,
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


def _serialize_composite_result(result: Any) -> dict[str, Any]:
    return {
        "composite_score": result.composite_score,
        "confidence": result.confidence,
        "direction": result.direction,
        "signal": result.signal,
        "votes": result.votes,
        "weights": result.weights,
        "dampening_multiplier": result.dampening_multiplier,
    }


def _hybrid_ai_bias(action: str | None) -> float | None:
    normalized = (action or "").strip().upper()
    if normalized == "BUY":
        return 1.0
    if normalized == "SELL":
        return -1.0
    if normalized == "HOLD":
        return 0.0
    return None


def _hybrid_ai_vote_value(decision: AIDecisionResult | None) -> float | None:
    if decision is None:
        return None
    return compute_ai_vote(_hybrid_ai_bias(decision.action), decision.confidence, 1.0)


def _update_strategy_streak(strategy: Strategy, pnl: Decimal | None) -> None:
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

    strategy.streak_size_multiplier = streak_multiplier_for_losses(strategy.consecutive_losses)


def _accumulate_wallet_losses(wallet: Any, pnl: Decimal | None) -> None:
    """Track daily/weekly losses on the wallet for limit enforcement."""
    if pnl is None or pnl >= 0:
        return
    loss = abs(pnl)
    wallet.daily_loss_usdt = (wallet.daily_loss_usdt or Decimal("0")) + loss
    wallet.weekly_loss_usdt = (wallet.weekly_loss_usdt or Decimal("0")) + loss


def _touch_ai_metrics(strategy: Strategy, decision: AIDecisionResult) -> None:
    if decision.usage is None:
        return

    usage = decision.usage
    strategy.ai_last_decision_at = datetime.now(timezone.utc)
    strategy.ai_last_decision_status = decision.status
    strategy.ai_last_reasoning = decision.reason or decision.raw_response
    strategy.ai_last_provider = usage.provider
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


def _build_ai_log(
    strategy_id: str,
    symbol: str,
    decision: AIDecisionResult | None = None,
    *,
    status: str | None = None,
    skip_reason: str | None = None,
    reason: str | None = None,
) -> AICallLog:
    if decision is not None:
        usage = decision.usage
        return AICallLog(
            strategy_id=strategy_id,
            symbol=symbol,
            status=decision.status,
            skip_reason=decision.skip_reason,
            action=decision.signal,
            confidence=Decimal(str(decision.confidence)) if decision.confidence is not None else None,
            reasoning=decision.reason or decision.raw_response,
            error=decision.error,
            provider=usage.provider if usage else None,
            model=usage.model if usage else None,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            cost_usdt=usage.estimated_cost_usdt if usage else Decimal("0"),
        )
    return AICallLog(
        strategy_id=strategy_id,
        symbol=symbol,
        status=status or "skipped",
        skip_reason=skip_reason,
        reasoning=reason,
    )


def _build_indicator_snapshot(indicators: dict[str, Any]) -> dict[str, Any]:
    """Extract key indicator values for trade log context."""
    snap: dict[str, Any] = {}
    for key in ("rsi", "atr", "volume_ratio"):
        vals = indicators.get(key)
        if isinstance(vals, (list, tuple)) and vals:
            snap[key] = round(float(vals[-1]), 4)
        elif isinstance(vals, (int, float)):
            snap[key] = round(float(vals), 4)

    for key in ("sma_short", "sma_long", "ema_short", "ema_long"):
        vals = indicators.get(key)
        if isinstance(vals, (list, tuple)) and vals:
            snap[key] = round(float(vals[-1]), 2)

    macd_line = indicators.get("macd_line")
    macd_signal = indicators.get("signal_line") or indicators.get("macd_signal")
    macd_hist = indicators.get("macd_histogram") or indicators.get("histogram")
    if isinstance(macd_line, (list, tuple)) and macd_line:
        snap["macd_line"] = round(float(macd_line[-1]), 4)
    if isinstance(macd_signal, (list, tuple)) and macd_signal:
        snap["macd_signal"] = round(float(macd_signal[-1]), 4)
    if isinstance(macd_hist, (list, tuple)) and macd_hist:
        snap["macd_histogram"] = round(float(macd_hist[-1]), 4)

    for key in ("bb_upper", "bb_middle", "bb_lower"):
        vals = indicators.get(key)
        if isinstance(vals, (list, tuple)) and vals:
            snap[key] = round(float(vals[-1]), 2)

    return snap


INTERVAL_TO_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400,
}

# Per-strategy lock to prevent concurrent execution of run_single_cycle
_strategy_locks: dict[str, asyncio.Lock] = {}


def _compute_equity(wallet: Any, position: Any, market_price: Decimal) -> Decimal:
    """Cash + mark-to-market position value."""
    equity = wallet.available_usdt
    if position is not None:
        equity += position.quantity * market_price
    return equity


async def _force_stop_loss_sell(
    session: Any,
    strategy: Strategy,
    strategy_id: str,
    wallet: Any,
    position: Any,
    symbol: str,
    market_price: Decimal,
    manager: Any,
) -> dict[str, Any]:
    """Execute an immediate full sell triggered by stop-loss."""
    from app.engine.executor import execute_sell  # already imported at module level

    config = strategy.config_json or {}
    result = await execute_sell(
        session, strategy_id, wallet, symbol, market_price,
        Decimal("1.0"),
        reason=f"Stop-loss triggered at {market_price} (stop={position.stop_loss_price})",
        strategy_name=strategy.name,
        strategy_type=config.get("strategy_type", "unknown"),
        decision_source="risk",
    )
    if result.success:
        _update_strategy_streak(strategy, result.trade.pnl)
        _accumulate_wallet_losses(wallet, result.trade.pnl)
        logger.info(
            "stop-loss executed strategy_id=%s symbol=%s price=%s stop=%s",
            strategy_id, symbol, market_price, position.stop_loss_price,
        )
        await session.commit()
        await manager.broadcast({
            "type": "trade_executed",
            "strategy_id": strategy_id,
            "action": "SELL",
            "symbol": symbol,
            "price": float(result.trade.price),
            "quantity": float(result.trade.quantity),
            "fee": float(result.trade.fee),
            "pnl": float(result.trade.pnl) if result.trade.pnl is not None else None,
            "reason": "stop_loss_triggered",
            "decision_source": "risk",
        })
        await manager.broadcast({
            "type": "position_changed",
            "strategy_id": strategy_id,
            "symbol": symbol,
            "has_position": False,
            "quantity": 0.0,
            "entry_price": None,
            "available_usdt": float(wallet.available_usdt),
        })
        return {
            "status": "executed",
            "action": "SELL",
            "reason": "stop_loss_triggered",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "risk",
            "price": str(result.trade.price),
            "pnl": str(result.trade.pnl) if result.trade.pnl else None,
        }
    await session.rollback()
    return {
        "status": "failed",
        "reason": f"Stop-loss sell failed: {result.error}",
        "symbol": symbol,
        "strategy_id": strategy_id,
        "decision_source": "risk",
    }


async def run_single_cycle(
    strategy_id: str,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    force: bool = False,
) -> dict[str, Any]:
    """Execute one decision cycle for a strategy."""
    # Acquire per-strategy lock to prevent duplicate concurrent trades
    if strategy_id not in _strategy_locks:
        _strategy_locks[strategy_id] = asyncio.Lock()
    lock = _strategy_locks[strategy_id]

    if lock.locked():
        logger.debug("cycle already running strategy_id=%s, skipping", strategy_id)
        return {
            "status": "skipped",
            "reason": "Cycle already in progress",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "concurrency_guard",
        }

    async with lock:
        owner_id = await _acquire_cycle_db_lock(strategy_id)
        if owner_id is None:
            logger.debug("database cycle lock busy strategy_id=%s, skipping", strategy_id)
            return {
                "status": "skipped",
                "reason": "Cycle already in progress in another worker",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "database_concurrency_guard",
            }

        try:
            return await _run_single_cycle_locked(strategy_id, symbol, interval, force)
        finally:
            await _release_cycle_db_lock(strategy_id, owner_id)


async def _run_single_cycle_locked(
    strategy_id: str,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    force: bool = False,
) -> dict[str, Any]:
    """Execute one decision cycle for a strategy (must be called under lock)."""
    store = DataStore.get_instance()
    manager = ConnectionManager.get_instance()
    candles = store.get_candles(symbol, interval)
    closes = [candle.close for candle in candles]

    if len(closes) < 50:
        logger.warning(
            "insufficient candles strategy_id=%s symbol=%s candles=%d required=50",
            strategy_id,
            symbol,
            len(closes),
        )
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

        # Override interval from strategy if set
        interval = strategy.candle_interval or (strategy.config_json or {}).get("candle_interval", interval)

        # Get strategy config
        config = strategy.config_json or {}
        strategy_type = config.get("strategy_type", "sma_crossover")
        ai_config = _normalize_ai_counters(strategy)

        # Get wallet and position
        wallet = await get_or_create_wallet(
            session, strategy_id, Decimal(str(config.get("initial_balance", 1000)))
        )
        position = await get_position(session, strategy_id, symbol)
        has_position = position is not None

        current_price = store.get_latest_price(symbol)
        if current_price is None:
            logger.warning("missing price symbol=%s strategy_id=%s", symbol, strategy_id)
            return {
                "status": "skipped",
                "reason": "No price data",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "market_data",
            }

        market_price = Decimal(str(current_price))

        # ── Risk check 1: Stop-loss ──────────────────────────────────────
        if (
            position is not None
            and position.stop_loss_price is not None
            and market_price <= position.stop_loss_price
        ):
            return await _force_stop_loss_sell(
                session, strategy, strategy_id, wallet, position, symbol, market_price, manager,
            )

        # ── Risk check 2: Max drawdown circuit breaker ───────────────────
        equity = _compute_equity(wallet, position, market_price)
        peak = wallet.peak_equity_usdt or equity
        if equity > peak:
            wallet.peak_equity_usdt = equity
            peak = equity
        if peak > 0:
            drawdown_pct = (peak - equity) / peak * 100
            max_dd = Decimal(str(strategy.max_drawdown_pct or settings.default_max_drawdown_pct))
            if drawdown_pct >= max_dd:
                await session.commit()
                logger.warning(
                    "max drawdown hit strategy_id=%s drawdown=%.2f%% limit=%s%%",
                    strategy_id, drawdown_pct, max_dd,
                )
                return {
                    "status": "halted",
                    "reason": f"Max drawdown {drawdown_pct:.2f}% exceeds limit {max_dd}%",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "risk",
                }

        # ── Risk check 3: Daily / weekly loss limits ──────────────────
        today = datetime.now(timezone.utc).date()
        if wallet.daily_loss_reset_date != today:
            wallet.daily_loss_usdt = Decimal("0")
            wallet.daily_loss_reset_date = today

        from datetime import timedelta
        week_start = today
        days_since_monday = today.weekday()  # Monday=0
        week_start = today - timedelta(days=days_since_monday)
        if wallet.weekly_loss_reset_date is None or wallet.weekly_loss_reset_date < week_start:
            wallet.weekly_loss_usdt = Decimal("0")
            wallet.weekly_loss_reset_date = week_start

        daily_limit = Decimal(str(config.get("daily_loss_limit_usdt", 0)))
        weekly_limit = Decimal(str(config.get("weekly_loss_limit_usdt", 0)))
        if daily_limit > 0 and wallet.daily_loss_usdt >= daily_limit:
            await session.commit()
            logger.warning(
                "daily loss limit hit strategy_id=%s loss=%s limit=%s",
                strategy_id, wallet.daily_loss_usdt, daily_limit,
            )
            return {
                "status": "halted",
                "reason": f"Daily loss ${wallet.daily_loss_usdt} exceeds limit ${daily_limit}",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "risk",
            }
        if weekly_limit > 0 and wallet.weekly_loss_usdt >= weekly_limit:
            await session.commit()
            logger.warning(
                "weekly loss limit hit strategy_id=%s loss=%s limit=%s",
                strategy_id, wallet.weekly_loss_usdt, weekly_limit,
            )
            return {
                "status": "halted",
                "reason": f"Weekly loss ${wallet.weekly_loss_usdt} exceeds limit ${weekly_limit}",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "risk",
            }

        # ── Compute indicators (pass highs/lows for ATR) ────────────────
        highs = [candle.high for candle in candles]
        lows = [candle.low for candle in candles]
        volumes = [candle.volume for candle in candles]
        indicators = compute_indicators(closes, config, highs=highs, lows=lows, volumes=volumes)

        if strategy_type == "hybrid_composite":
            ai_result: AIDecisionResult | None = None
            flat_metrics: dict[str, float] | None = None
            # Pre-compute composite score WITHOUT AI so we can pass it to the AI
            pre_composite = compute_composite_score(indicators, config=config, ai_vote_value=None)
            if ai_config["ai_enabled"]:
                flat_metrics = analyze_flat_market(
                    closes,
                    ai_config["flat_market_threshold_pct"],
                    indicators.get("atr"),
                )[1]
                cooldown_remaining = _cooldown_remaining(strategy, ai_config["ai_cooldown_seconds"])
                if cooldown_remaining <= 0 or force:
                    ai_context = build_ai_context(
                        strategy_id=strategy.id,
                        strategy_name=strategy.name,
                        symbol=symbol,
                        interval=interval,
                        closes=closes,
                        highs=highs,
                        lows=lows,
                        volumes=volumes,
                        indicators=indicators,
                        wallet_available_usdt=wallet.available_usdt,
                        has_position=has_position,
                        position_quantity=position.quantity if position else None,
                        position_entry_price=position.entry_price if position else None,
                        current_price=market_price,
                        ai_strategy_key=ai_config["ai_strategy_key"],
                        ai_provider=ai_config["ai_provider"],
                        ai_model=ai_config["ai_model"],
                        ai_cooldown_seconds=ai_config["ai_cooldown_seconds"],
                        ai_max_tokens=ai_config["ai_max_tokens"],
                        ai_temperature=ai_config["ai_temperature"],
                        flat_market_metrics=flat_metrics or {
                            "threshold_pct": ai_config["flat_market_threshold_pct"]
                        },
                        algorithmic_signal={
                            "composite_score": round(pre_composite.composite_score, 4),
                            "confidence": round(pre_composite.confidence, 4),
                            "signal": pre_composite.signal,
                            "direction": pre_composite.direction,
                            "votes": {k: round(v, 4) for k, v in pre_composite.votes.items()},
                            "dampening_multiplier": pre_composite.dampening_multiplier,
                        },
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
                    else:
                        _touch_ai_metrics(strategy, ai_result)
                    session.add(_build_ai_log(strategy.id, symbol, ai_result))
                    await session.commit()
                else:
                    session.add(_build_ai_log(
                        strategy.id, symbol,
                        status="skipped", skip_reason="cooldown",
                        reason=f"AI cooldown active ({cooldown_remaining}s remaining)",
                    ))
                    await session.commit()

            composite_result = compute_composite_score(
                indicators,
                config=config,
                ai_vote_value=_hybrid_ai_vote_value(ai_result),
            )

            if position is not None:
                prior_trailing_stop = position.trailing_stop_price
                exit_decision = evaluate_exit(
                    position=position,
                    current_price=market_price,
                    composite_score=composite_result.composite_score,
                    config=config,
                    now=datetime.now(timezone.utc),
                )

                if (
                    exit_decision.updated_trailing_stop_price is not None
                    and exit_decision.updated_trailing_stop_price != prior_trailing_stop
                ):
                    position.trailing_stop_price = exit_decision.updated_trailing_stop_price
                    await session.flush()

                if exit_decision.action == "SELL":
                    result = await execute_sell(
                        session,
                        strategy_id,
                        wallet,
                        symbol,
                        market_price,
                        exit_decision.quantity_pct,
                        reason=exit_decision.reason,
                        strategy_name=strategy.name,
                        strategy_type=strategy_type,
                        decision_source="hybrid_exit",
                        indicator_snapshot=_build_indicator_snapshot(indicators),
                        composite_score=Decimal(str(round(composite_result.composite_score, 4))),
                        composite_confidence=Decimal(str(round(composite_result.confidence, 4))),
                    )
                    if result.success:
                        _update_strategy_streak(strategy, result.trade.pnl)
                        _accumulate_wallet_losses(wallet, result.trade.pnl)
                        refreshed_position = await get_position(session, strategy_id, symbol)
                        if refreshed_position is not None:
                            if exit_decision.consume_take_profit:
                                refreshed_position.take_profit_price = None
                            if exit_decision.updated_trailing_stop_price is not None:
                                refreshed_position.trailing_stop_price = exit_decision.updated_trailing_stop_price

                        await session.commit()
                        refreshed_position = await get_position(session, strategy_id, symbol)
                        await manager.broadcast(
                            {
                                "type": "trade_executed",
                                "strategy_id": strategy_id,
                                "action": "SELL",
                                "symbol": symbol,
                                "price": float(result.trade.price),
                                "quantity": float(result.trade.quantity),
                                "fee": float(result.trade.fee),
                                "pnl": float(result.trade.pnl) if result.trade.pnl is not None else None,
                                "reason": exit_decision.reason,
                                "decision_source": "hybrid_exit",
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
                            "action": "SELL",
                            "symbol": symbol,
                            "price": str(result.trade.price),
                            "quantity": str(result.trade.quantity),
                            "fee": str(result.trade.fee),
                            "pnl": str(result.trade.pnl) if result.trade.pnl else None,
                            "reason": exit_decision.reason,
                            "decision_source": "hybrid_exit",
                            "composite": _serialize_composite_result(composite_result),
                        }

                    await session.rollback()
                    return {
                        "status": "failed",
                        "reason": result.error,
                        "strategy_id": strategy_id,
                        "symbol": symbol,
                        "decision_source": "hybrid_exit",
                        "composite": _serialize_composite_result(composite_result),
                    }

                if (
                    exit_decision.updated_trailing_stop_price is not None
                    and exit_decision.updated_trailing_stop_price != prior_trailing_stop
                ):
                    await session.commit()
                    return {
                        "status": "hold",
                        "reason": "Trailing stop updated",
                        "symbol": symbol,
                        "strategy_id": strategy_id,
                        "decision_source": "hybrid_exit",
                        "composite": _serialize_composite_result(composite_result),
                    }

                return {
                    "status": "hold",
                    "reason": "Position open; no hybrid exit signal",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "hybrid_exit",
                    "composite": _serialize_composite_result(composite_result),
                }

            # ── Conflict gate: AI and algorithm must agree to trade ──
            ai_action = (ai_result.action or "HOLD").upper() if ai_result else "HOLD"
            algo_direction = pre_composite.signal  # computed WITHOUT AI vote (gated)
            if ai_action != "HOLD" and algo_direction != "HOLD" and ai_action != algo_direction:
                return {
                    "status": "hold",
                    "reason": (
                        f"AI/algorithm conflict: AI says {ai_action} but "
                        f"algorithm says {algo_direction} (score={pre_composite.composite_score:.3f}). "
                        f"No trade executed."
                    ),
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "conflict_gate",
                    "composite": _serialize_composite_result(composite_result),
                }

            if composite_result.signal != "BUY":
                return {
                    "status": "hold",
                    "reason": "Hybrid composite gate not met",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "hybrid_entry",
                    "composite": _serialize_composite_result(composite_result),
                }

            atr_values = indicators.get("atr", [])
            if not atr_values:
                return {
                    "status": "skipped",
                    "reason": "ATR unavailable for hybrid sizing",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "hybrid_entry",
                    "composite": _serialize_composite_result(composite_result),
                }

            take_profit_ratio = Decimal(str(config.get("take_profit_ratio", 2.0)))
            min_reward_risk_ratio = Decimal(str(config.get("min_reward_risk_ratio", 1.5)))
            if take_profit_ratio < min_reward_risk_ratio:
                return {
                    "status": "skipped",
                    "reason": "Configured reward/risk ratio below minimum",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "hybrid_entry",
                    "composite": _serialize_composite_result(composite_result),
                }

            # Map composite confidence to position sizing tiers
            comp_conf = composite_result.confidence
            confidence_tier = (
                "full" if comp_conf >= 0.8
                else "reduced" if comp_conf >= 0.6
                else "small"
            )

            sizing = calculate_position_size(
                equity=equity,
                entry_price=market_price,
                atr=Decimal(str(atr_values[-1])),
                atr_multiplier=Decimal(str(config.get("atr_stop_multiplier", 2.0))),
                risk_per_trade_pct=Decimal(str(strategy.risk_per_trade_pct)),
                confidence_tier=confidence_tier,
                losing_streak_count=strategy.consecutive_losses,
                max_position_pct=Decimal(str(strategy.max_position_size_pct)),
                take_profit_ratio=take_profit_ratio,
            )

            if sizing.quantity_pct <= Decimal("0"):
                return {
                    "status": "skipped",
                    "reason": "Hybrid sizing produced zero quantity",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "hybrid_entry",
                    "composite": _serialize_composite_result(composite_result),
                }

            result = await execute_buy(
                session,
                strategy_id,
                wallet,
                symbol,
                market_price,
                sizing.quantity_pct,
                reason=(
                    f"Hybrid BUY score={composite_result.composite_score:.3f} "
                    f"confidence={composite_result.confidence:.3f}"
                ),
                strategy_name=strategy.name,
                strategy_type=strategy_type,
                decision_source="hybrid_entry",
                indicator_snapshot=_build_indicator_snapshot(indicators),
                composite_score=Decimal(str(round(composite_result.composite_score, 4))),
                composite_confidence=Decimal(str(round(composite_result.confidence, 4))),
            )

            if result.success:
                refreshed_position = await get_position(session, strategy_id, symbol)
                if refreshed_position is not None:
                    refreshed_position.stop_loss_price = sizing.stop_loss_price
                    refreshed_position.take_profit_price = sizing.take_profit_price
                    refreshed_position.trailing_stop_price = None
                    refreshed_position.entry_atr = sizing.entry_atr

                await session.commit()
                refreshed_position = await get_position(session, strategy_id, symbol)
                new_equity = _compute_equity(wallet, refreshed_position, market_price)
                if new_equity > wallet.peak_equity_usdt:
                    wallet.peak_equity_usdt = new_equity
                    await session.commit()

                await manager.broadcast(
                    {
                        "type": "trade_executed",
                        "strategy_id": strategy_id,
                        "action": "BUY",
                        "symbol": symbol,
                        "price": float(result.trade.price),
                        "quantity": float(result.trade.quantity),
                        "fee": float(result.trade.fee),
                        "pnl": None,
                        "reason": result.trade.ai_reasoning,
                        "decision_source": "hybrid_entry",
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
                    "action": "BUY",
                    "symbol": symbol,
                    "price": str(result.trade.price),
                    "quantity": str(result.trade.quantity),
                    "fee": str(result.trade.fee),
                    "pnl": None,
                    "reason": result.trade.ai_reasoning,
                    "decision_source": "hybrid_entry",
                    "composite": _serialize_composite_result(composite_result),
                    "signal": _serialize_signal_result(
                        {
                            "action": "BUY",
                            "symbol": symbol,
                            "quantity_pct": sizing.quantity_pct,
                            "reason": result.trade.ai_reasoning or "",
                        }
                    ),
                }

            await session.rollback()
            return {
                "status": "failed",
                "reason": result.error,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "decision_source": "hybrid_entry",
                "composite": _serialize_composite_result(composite_result),
            }

        if ai_config["ai_enabled"] and strategy_type != "hybrid_composite":
            _, flat_metrics = analyze_flat_market(closes, ai_config["flat_market_threshold_pct"])
            cooldown_remaining = _cooldown_remaining(strategy, ai_config["ai_cooldown_seconds"])
            if cooldown_remaining > 0 and not force:
                session.add(_build_ai_log(
                    strategy.id, symbol,
                    status="skipped", skip_reason="cooldown",
                    reason=f"AI cooldown active ({cooldown_remaining}s remaining)",
                ))
                await session.commit()
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
                highs=highs,
                lows=lows,
                volumes=volumes,
                indicators=indicators,
                wallet_available_usdt=wallet.available_usdt,
                has_position=has_position,
                position_quantity=position.quantity if position else None,
                position_entry_price=position.entry_price if position else None,
                current_price=market_price,
                ai_strategy_key=ai_config["ai_strategy_key"],
                ai_provider=ai_config["ai_provider"],
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
                session.add(_build_ai_log(strategy.id, symbol, ai_result))
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
            session.add(_build_ai_log(strategy.id, symbol, ai_result))

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

        # ── Risk check 3: Position size cap for BUY signals ──────────────
        if signal.action.value == "BUY":
            max_pos_pct = Decimal(str(
                strategy.max_position_size_pct or settings.default_max_position_size_pct
            )) / 100
            max_spend = equity * max_pos_pct
            if wallet.available_usdt > 0:
                capped_pct = min(signal.quantity_pct, max_spend / wallet.available_usdt)
                if capped_pct < signal.quantity_pct:
                    logger.info(
                        "position size capped strategy_id=%s original=%.2f capped=%.2f",
                        strategy_id, signal.quantity_pct, capped_pct,
                    )
                signal.quantity_pct = max(capped_pct, Decimal("0"))

        # Execute
        _decision_source = "ai" if ai_config["ai_enabled"] else "rule"
        _trade_log_kwargs = dict(
            strategy_name=strategy.name,
            strategy_type=strategy_type,
            decision_source=_decision_source,
            indicator_snapshot=_build_indicator_snapshot(indicators),
        )
        if signal.action.value == "BUY":
            result = await execute_buy(
                session, strategy_id, wallet, symbol, market_price,
                signal.quantity_pct, reason=signal.reason,
                **_trade_log_kwargs,
            )
        else:
            result = await execute_sell(
                session, strategy_id, wallet, symbol, market_price,
                signal.quantity_pct, reason=signal.reason,
                **_trade_log_kwargs,
            )

        if result.success:
            logger.info(
                "trade executed strategy_id=%s action=%s symbol=%s price=%s quantity=%s fee=%s source=%s",
                strategy_id,
                signal.action.value,
                symbol,
                result.trade.price,
                result.trade.quantity,
                result.trade.fee,
                "ai" if ai_config["ai_enabled"] else "rule",
            )

            # ── Risk check 4: Set stop-loss on new BUY position ─────────
            if signal.action.value == "BUY":
                refreshed_position = await get_position(session, strategy_id, symbol)
                if refreshed_position is not None:
                    sl_pct = Decimal(str(
                        strategy.stop_loss_pct or settings.default_stop_loss_pct
                    )) / 100
                    refreshed_position.stop_loss_price = (
                        refreshed_position.entry_price * (1 - sl_pct)
                    ).quantize(Decimal("0.00000001"))
            else:
                _update_strategy_streak(strategy, result.trade.pnl)
                _accumulate_wallet_losses(wallet, result.trade.pnl)

            await session.commit()
            refreshed_position = await get_position(session, strategy_id, symbol)

            # ── Risk check 5: Update peak equity after trade ─────────────
            new_equity = _compute_equity(wallet, refreshed_position, market_price)
            if new_equity > wallet.peak_equity_usdt:
                wallet.peak_equity_usdt = new_equity
                await session.commit()

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
            logger.warning(
                "trade rejected strategy_id=%s symbol=%s error=%s",
                strategy_id,
                symbol,
                result.error,
            )
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


async def strategy_loop(strategy_id: str, interval_seconds: int = 3600) -> None:
    """Continuous trading loop for a single strategy."""
    # Ensure loop never runs faster than the smallest candle interval (1m = 60s)
    interval_seconds = max(interval_seconds, 60)
    symbol = "BTCUSDT"
    cycle = 0

    from app.strategies.manager import StrategyManager

    while True:
        try:
            lock = StrategyManager.get_instance().get_lock(strategy_id)
            async with lock:
                result = await run_single_cycle(strategy_id, symbol)
            cycle += 1

            if result.get("status") == "executed":
                logger.info(
                    "cycle complete strategy_id=%s cycle=%d status=executed action=%s",
                    strategy_id,
                    cycle,
                    result.get("action"),
                )
                # Snapshot after every trade
                await take_equity_snapshot(strategy_id, symbol)
            elif result.get("status") in {"skipped", "hold"}:
                logger.debug(
                    "cycle complete strategy_id=%s cycle=%d status=%s reason=%s",
                    strategy_id,
                    cycle,
                    result.get("status"),
                    result.get("reason"),
                )

            # Snapshot every cycle
            await take_equity_snapshot(strategy_id, symbol)

        except Exception:
            logger.exception("strategy loop crashed strategy_id=%s", strategy_id)

        await asyncio.sleep(interval_seconds)
