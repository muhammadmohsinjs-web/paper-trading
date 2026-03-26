"""Engine control endpoints — start/stop all strategies, manual trigger."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db_session
from app.engine.multi_coin import get_daily_picks, resolve_primary_symbol
from app.engine.ai_runtime import (
    build_ai_context,
    evaluate_ai_decision,
    normalize_ai_strategy_key,
    resolve_runtime_provider_and_model,
)
from app.engine.trading_loop import run_single_cycle
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.models.position import Position
from app.models.strategy import Strategy
from app.models.wallet import Wallet
from app.strategies.manager import StrategyManager

router = APIRouter(prefix="/engine", tags=["engine"])
settings = get_settings()


@router.post("/start")
async def start_engine():
    manager = StrategyManager.get_instance()
    count = await manager.start_all_active()
    return {"status": "started", "strategies_started": count}


@router.post("/stop")
async def stop_engine():
    manager = StrategyManager.get_instance()
    count = await manager.stop_all()
    return {"status": "stopped", "strategies_stopped": count}


@router.get("/status")
async def engine_status():
    manager = StrategyManager.get_instance()
    running = manager.running_strategies()
    return {"running_strategies": running, "count": len(running)}


@router.post("/strategies/{strategy_id}/execute")
async def manual_execute(
    strategy_id: str,
    force: bool = Query(False, description="Bypass AI cooldown, but still respect flat-market gating."),
    session: AsyncSession = Depends(get_db_session),
):
    """Manually trigger one strategy decision cycle."""
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    lock = StrategyManager.get_instance().get_lock(strategy_id)
    if lock.locked():
        return {"status": "skipped", "reason": "Strategy cycle already in progress"}
    async with lock:
        return await run_single_cycle(strategy_id, force=force)


@router.post("/strategies/{strategy_id}/ai-preview")
async def ai_preview(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Make a standalone AI API call and return its analysis — no trade is executed.

    This lets users see what the AI thinks about the current market without
    actually placing any orders.
    """
    # Load strategy
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    config = strategy.config_json or {}
    daily_picks = await get_daily_picks(session, strategy)
    symbol = daily_picks[0].symbol if daily_picks else resolve_primary_symbol(strategy)
    interval = strategy.candle_interval or settings.default_candle_interval

    # Get market data from the store
    store = DataStore.get_instance()
    candles = store.get_candles(symbol, interval)
    if not candles or len(candles) < 50:
        raise HTTPException(400, "Not enough candle data for AI analysis")

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]
    market_price = Decimal(str(closes[-1]))

    # Compute indicators
    indicators = compute_indicators(closes, config, highs=highs, lows=lows, volumes=volumes)

    # Get wallet & position
    wallet_result = await session.execute(
        select(Wallet).where(Wallet.strategy_id == strategy_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    available_usdt = wallet.available_usdt if wallet else Decimal("1000")

    position_result = await session.execute(
        select(Position).where(
            Position.strategy_id == strategy_id,
            Position.symbol == symbol,
        )
    )
    position = position_result.scalar_one_or_none()

    # Resolve AI config
    provider, ai_model = resolve_runtime_provider_and_model(
        {
            "strategy": {
                "ai_provider": strategy.ai_provider or config.get("ai_provider"),
                "ai_model": strategy.ai_model or config.get("ai_model"),
            }
        }
    )
    ai_strategy_key = normalize_ai_strategy_key(
        strategy.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type")
    )
    ai_cooldown = int(strategy.ai_cooldown_seconds or config.get("ai_cooldown_seconds") or 60)
    ai_max_tokens = int(strategy.ai_max_tokens or config.get("ai_max_tokens") or settings.ai_max_tokens)
    ai_temperature = Decimal(str(strategy.ai_temperature or config.get("ai_temperature", 0.2)))

    # Build context
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
        wallet_available_usdt=available_usdt,
        has_position=position is not None,
        position_quantity=position.quantity if position else None,
        position_entry_price=position.entry_price if position else None,
        current_price=market_price,
        ai_strategy_key=ai_strategy_key,
        ai_provider=provider,
        ai_model=ai_model,
        ai_cooldown_seconds=ai_cooldown,
        ai_max_tokens=ai_max_tokens,
        ai_temperature=ai_temperature,
        flat_market_metrics={"threshold_pct": settings.ai_flat_market_threshold_pct},
    )

    # Call AI (force=True to bypass flat market gating for preview)
    ai_result = await evaluate_ai_decision(
        strategy_key=ai_strategy_key,
        context=ai_context,
        force=True,
    )

    # Update strategy AI tracking fields
    if ai_result.usage is not None:
        strategy.ai_last_decision_at = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        strategy.ai_last_decision_status = ai_result.status
        strategy.ai_last_reasoning = ai_result.reason
        strategy.ai_last_provider = provider
        strategy.ai_last_model = ai_model
        strategy.ai_last_prompt_tokens = ai_result.usage.prompt_tokens
        strategy.ai_last_completion_tokens = ai_result.usage.completion_tokens
        strategy.ai_last_total_tokens = ai_result.usage.total_tokens
        strategy.ai_last_cost_usdt = ai_result.usage.estimated_cost_usdt
        strategy.ai_total_calls = (strategy.ai_total_calls or 0) + 1
        strategy.ai_total_prompt_tokens = (strategy.ai_total_prompt_tokens or 0) + ai_result.usage.prompt_tokens
        strategy.ai_total_completion_tokens = (strategy.ai_total_completion_tokens or 0) + ai_result.usage.completion_tokens
        strategy.ai_total_tokens = (strategy.ai_total_tokens or 0) + ai_result.usage.total_tokens
        strategy.ai_total_cost_usdt = (strategy.ai_total_cost_usdt or Decimal("0")) + ai_result.usage.estimated_cost_usdt
        await session.commit()

    # Build response
    usage_data = None
    if ai_result.usage:
        usage_data = {
            "provider": ai_result.usage.provider,
            "model": ai_result.usage.model,
            "prompt_tokens": ai_result.usage.prompt_tokens,
            "completion_tokens": ai_result.usage.completion_tokens,
            "total_tokens": ai_result.usage.total_tokens,
            "estimated_cost_usdt": float(ai_result.usage.estimated_cost_usdt),
        }

    return {
        "status": ai_result.status,
        "action": ai_result.action,
        "symbol": symbol,
        "confidence": ai_result.confidence,
        "reason": ai_result.reason,
        "raw_response": ai_result.raw_response,
        "usage": usage_data,
        "error": ai_result.error,
        "strategy_key": ai_strategy_key,
        "preview_only": True,
    }
