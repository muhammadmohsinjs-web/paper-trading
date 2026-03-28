"""Main trading loop — one asyncio.Task per strategy.

Refactored to delegate to extracted components:
- HybridCompositeStrategy (strategies/hybrid_composite.py)
- PostTradePipeline (engine/post_trade.py)
- StrategyContext (strategies/base.py)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text

from app.api.ws import ConnectionManager
from app.config import default_ai_model_for_provider, get_settings, normalize_ai_provider
from app.database import (
    SessionLocal,
    commit_with_write_lock,
    execute_with_write_lock,
)
from app.engine.ai_runtime import (
    AIValidationResult,
    AIUsage,
    build_ai_context,
    analyze_flat_market,
    evaluate_ai_validation,
    normalize_ai_strategy_key,
)
from app.engine.economic_viability import EconomicViabilityResult, evaluate_economic_viability
from app.engine.evaluation_logging import build_symbol_evaluation_log
from app.engine.multi_coin import (
    MULTI_COIN_MODE,
    build_portfolio_positions,
    compute_total_equity,
    ensure_coordinated_picks_fresh,
    ensure_daily_picks,
    resolve_execution_mode,
    resolve_max_concurrent_positions,
    resolve_primary_symbol,
)
from app.engine.executor import execute_buy, execute_sell
from app.engine.exit_manager import evaluate_exit
from app.engine.position_sizer import (
    PositionSizingSafetyResult,
    calculate_exit_levels,
    calculate_position_size,
    calculate_scaled_exit_levels,
    evaluate_position_sizing_safety,
)
from app.engine.post_trade import (
    compute_equity,
    handle_post_trade,
)
from app.engine.safety_validator import SafetyVerdict, evaluate_local_trade_safety
from app.engine.reason_codes import AI_SAFETY_UNAVAILABLE
from app.engine.tradability import (
    MovementQuality,
    TradabilityResult,
    evaluate_movement_quality,
    evaluate_symbol_tradability,
)
from app.engine.wallet_manager import get_or_create_wallet, get_position, get_positions
from app.models.ai_call_log import AICallLog
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.regime.classifier import RegimeClassifier
from app.regime.types import MarketRegime, RegimeResult
from app.risk.portfolio import PortfolioRiskManager
from app.strategies.base import StrategyContext
from app.strategies.hybrid_composite import HybridCompositeStrategy, HybridDecision
from app.strategies.registry import get_strategy_class
from app.engine.mtf_confluence import check_confluence

_regime_classifier = RegimeClassifier()

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
        "ai_model": str(default_ai_model_for_provider(ai_provider, settings)),
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
        "directional_score": getattr(result, "directional_score", result.composite_score),
        "edge_strength": getattr(result, "edge_strength", 0.0),
        "base_edge_score": getattr(result, "base_edge_score", 0.0),
        "signal_agreement": getattr(result, "signal_agreement", 0.0),
        "market_quality": getattr(result, "market_quality", 0.0),
        "regime_alignment": getattr(result, "regime_alignment", 0.0),
        "edge_floor_passed": getattr(result, "edge_floor_passed", False),
        "quality_floor_passed": getattr(result, "quality_floor_passed", False),
        "reject_reason_codes": getattr(result, "reject_reason_codes", []),
    }


@dataclass
class LiveTradeDecision:
    action: str
    reason: str
    raw_confidence: float
    final_confidence: float
    regime: str
    quantity_pct: Decimal = Decimal("0")
    validator_reason: str | None = None
    decision_source: str = "rule_entry"
    composite_result: Any | None = None
    entry_confidence_bucket: str | None = None


@dataclass
class ExecutionReadiness:
    tradability_passed: bool
    signal_quality_passed: bool
    economic_viability_passed: bool
    ai_safety_passed: bool
    sizing_passed: bool
    fatal_flags: list[str]
    reason_codes: list[str]
    reason_text: str
    metrics: dict[str, Any]


def _first_reason_code(reason_codes: list[str] | None) -> str | None:
    if not reason_codes:
        return None
    return reason_codes[0]


def _join_reason_codes(reason_codes: list[str]) -> str:
    return "; ".join(reason_codes) if reason_codes else "Checks passed"


def _log_stage(
    session: Any,
    *,
    strategy_id: str,
    cycle_id: str,
    symbol: str,
    stage: str,
    status: str,
    reason_code: str | None = None,
    reason_text: str | None = None,
    metrics_json: dict[str, Any] | None = None,
    context_json: dict[str, Any] | None = None,
) -> None:
    session.add(
        build_symbol_evaluation_log(
            strategy_id=strategy_id,
            cycle_id=cycle_id,
            symbol=symbol,
            stage=stage,
            status=status,
            reason_code=reason_code,
            reason_text=reason_text,
            metrics_json=metrics_json,
            context_json=context_json,
        )
    )


def _build_execution_readiness(
    *,
    tradability: TradabilityResult,
    signal_quality_passed: bool,
    economic_viability: EconomicViabilityResult,
    ai_safety: SafetyVerdict,
    sizing_safety: PositionSizingSafetyResult,
) -> ExecutionReadiness:
    reason_codes: list[str] = []
    if not tradability.passed:
        reason_codes.extend(tradability.reason_codes)
    if not signal_quality_passed:
        reason_codes.append("FINAL_SANITY_FAILED")
    if not economic_viability.passed:
        reason_codes.extend(economic_viability.reason_codes)
    if not ai_safety.approved:
        if ai_safety.reason_code:
            reason_codes.append(ai_safety.reason_code)
        if ai_safety.fatal_flags:
            reason_codes.extend(ai_safety.fatal_flags)
    if not sizing_safety.passed and sizing_safety.reason_code:
        reason_codes.append(sizing_safety.reason_code)

    deduped_codes = list(dict.fromkeys(reason_codes))
    fatal_flags = list(dict.fromkeys(ai_safety.fatal_flags or []))
    return ExecutionReadiness(
        tradability_passed=tradability.passed,
        signal_quality_passed=signal_quality_passed,
        economic_viability_passed=economic_viability.passed,
        ai_safety_passed=ai_safety.approved,
        sizing_passed=sizing_safety.passed,
        fatal_flags=fatal_flags,
        reason_codes=deduped_codes,
        reason_text=_join_reason_codes(deduped_codes),
        metrics={
            "tradability": tradability.to_dict(),
            "economic_viability": economic_viability.to_dict(),
            "ai_safety": ai_safety.to_dict(),
            "sizing_safety": {
                "passed": sizing_safety.passed,
                "reason_code": sizing_safety.reason_code,
                "reason_text": sizing_safety.reason_text,
                "atr_pct": float(sizing_safety.atr_pct),
                "stop_distance_pct": float(sizing_safety.stop_distance_pct),
                "take_profit_distance_pct": float(sizing_safety.take_profit_distance_pct),
                "min_atr_pct": float(sizing_safety.min_atr_pct),
                "min_stop_distance_pct": float(sizing_safety.min_stop_distance_pct),
                "min_take_profit_distance_pct": float(sizing_safety.min_take_profit_distance_pct),
            },
        },
    )


def _touch_ai_metrics(
    strategy: Strategy,
    *,
    status: str,
    reason: str | None,
    usage: AIUsage | None,
) -> None:
    strategy.ai_last_decision_status = status
    strategy.ai_last_reasoning = reason
    if usage is None:
        return

    strategy.ai_last_decision_at = datetime.now(timezone.utc)
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


def _build_ai_validation_log(
    strategy_id: str,
    symbol: str,
    validation: AIValidationResult | None = None,
    *,
    status: str | None = None,
    skip_reason: str | None = None,
    reason: str | None = None,
    proposed_action: str | None = None,
) -> AICallLog:
    if validation is not None:
        usage = validation.usage
        return AICallLog(
            strategy_id=strategy_id,
            symbol=symbol,
            status=validation.status,
            skip_reason=validation.skip_reason,
            action=proposed_action,
            confidence=None,
            reasoning=validation.reason or validation.raw_response,
            error=validation.error,
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


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _signal_confidence(signal: Any) -> float:
    quantity_pct = getattr(signal, "quantity_pct", Decimal("0"))
    if getattr(getattr(signal, "action", None), "value", getattr(signal, "action", None)) == "SELL":
        return 1.0
    return _clamp_confidence(float(quantity_pct))


def _base_entry_gate(strategy_type: str, config: dict[str, Any]) -> float:
    default_gate = 0.35 if strategy_type == "hybrid_composite" else 0.30
    return float(config.get("confidence_gate", default_gate))


def _confidence_bucket(confidence: float) -> str:
    bounded = min(max(confidence, 0.0), 0.9999)
    lower = int(bounded * 10) * 10
    return f"{lower:02d}-{lower + 9:02d}"


def _hybrid_calibration_multiplier(config: dict[str, Any], bucket: str) -> float:
    calibration = (config.get("hybrid_confidence_calibration") or {}).get(bucket, {})
    trades = int(calibration.get("trades", 0) or 0)
    if trades < 20:
        return 1.0
    win_rate = float(calibration.get("wins", 0) or 0) / trades if trades > 0 else 0.0
    return max(0.75, min(1.25, 0.75 + 0.50 * win_rate))


def _update_hybrid_calibration(strategy: Strategy, position: Any, trade: Any) -> None:
    bucket = getattr(position, "entry_confidence_bucket", None)
    pnl_pct = getattr(trade, "pnl_pct", None)
    if not bucket or pnl_pct is None:
        return

    config = dict(strategy.config_json or {})
    calibration = dict(config.get("hybrid_confidence_calibration") or {})
    stats = dict(calibration.get(bucket) or {})
    trades = int(stats.get("trades", 0) or 0) + 1
    wins = int(stats.get("wins", 0) or 0) + (1 if (trade.pnl or Decimal("0")) > 0 else 0)
    prev_avg = float(stats.get("avg_pnl_pct", 0.0) or 0.0)
    next_avg = ((prev_avg * (trades - 1)) + float(pnl_pct)) / trades
    calibration[bucket] = {
        "trades": trades,
        "wins": wins,
        "avg_pnl_pct": round(next_avg, 6),
    }
    config["hybrid_confidence_calibration"] = calibration
    strategy.config_json = config


def _refresh_loss_counters(wallet: Any) -> None:
    today = datetime.now(timezone.utc).date()
    if wallet.daily_loss_reset_date != today:
        wallet.daily_loss_usdt = Decimal("0")
        wallet.daily_loss_reset_date = today

    week_start = today - timedelta(days=today.weekday())
    if wallet.weekly_loss_reset_date is None or wallet.weekly_loss_reset_date < week_start:
        wallet.weekly_loss_usdt = Decimal("0")
        wallet.weekly_loss_reset_date = week_start


def _entry_risk_status(
    strategy: Strategy,
    wallet: Any,
    equity: Decimal,
    config: dict[str, Any],
) -> str | None:
    peak = wallet.peak_equity_usdt or equity
    if equity > peak:
        wallet.peak_equity_usdt = equity
        peak = equity
    if peak > 0:
        drawdown_pct = (peak - equity) / peak * 100
        max_dd = Decimal(str(strategy.max_drawdown_pct or settings.default_max_drawdown_pct))
        if drawdown_pct >= max_dd:
            return f"Max drawdown {drawdown_pct:.2f}% exceeds limit {max_dd}%"

    _refresh_loss_counters(wallet)
    daily_limit = Decimal(str(config.get("daily_loss_limit_usdt", 0)))
    weekly_limit = Decimal(str(config.get("weekly_loss_limit_usdt", 0)))
    if daily_limit > 0 and wallet.daily_loss_usdt >= daily_limit:
        return f"Daily loss ${wallet.daily_loss_usdt} exceeds limit ${daily_limit}"
    if weekly_limit > 0 and wallet.weekly_loss_usdt >= weekly_limit:
        return f"Weekly loss ${wallet.weekly_loss_usdt} exceeds limit ${weekly_limit}"
    return None


def _check_reentry_cooldown(
    strategy: Strategy,
    symbol: str,
    candle_interval: str,
    cooldown_candles: int = 6,
) -> tuple[bool, str]:
    """Block re-entry on the same symbol within N candles of a stop-loss."""
    if not strategy.last_stop_loss_at or strategy.last_stop_loss_symbol != symbol:
        return True, ""
    interval_seconds = INTERVAL_TO_SECONDS.get(candle_interval, 300)
    elapsed = (datetime.now(timezone.utc) - strategy.last_stop_loss_at).total_seconds()
    cooldown_seconds = interval_seconds * cooldown_candles
    if elapsed < cooldown_seconds:
        remaining = int(cooldown_seconds - elapsed)
        return False, f"Re-entry cooldown: {remaining}s remaining after stop-loss on {symbol}"
    return True, ""


def _regime_entry_policy(
    strategy_type: str,
    regime: MarketRegime,
    base_gate: float,
) -> tuple[bool, Decimal, float, str | None]:
    if regime == MarketRegime.CRASH:
        # CRASH: only allow reversal strategies with very small size and high gate
        if strategy_type in {"rsi_mean_reversion", "bollinger_bounce"}:
            return True, Decimal("0.2"), base_gate + 0.20, None
        return False, Decimal("1.0"), base_gate, f"{regime.value} blocks new long entries"

    if regime == MarketRegime.TRENDING_DOWN:
        # Allow reversal/mean-reversion strategies with reduced size and raised gate
        if strategy_type in {"rsi_mean_reversion", "bollinger_bounce", "macd_momentum"}:
            return True, Decimal("0.3"), base_gate + 0.15, None
        return False, Decimal("1.0"), base_gate, f"{regime.value} blocks new long entries"

    if regime == MarketRegime.HIGH_VOLATILITY:
        if strategy_type not in {"hybrid_composite", "macd_momentum", "bollinger_bounce"}:
            return False, Decimal("1.0"), base_gate + 0.10, "High volatility blocks this strategy"
        return True, Decimal("0.5"), base_gate + 0.10, None

    if regime == MarketRegime.RANGING:
        if strategy_type in {"sma_crossover", "macd_momentum"}:
            return True, Decimal("0.5"), base_gate + 0.05, None  # Allow with half size and slightly raised gate
        return True, Decimal("1.0"), base_gate, None

    if regime == MarketRegime.TRENDING_UP:
        # All strategies can trade in uptrends; pullback strategies use reduced size
        if strategy_type in {"rsi_mean_reversion", "bollinger_bounce"}:
            return True, Decimal("0.5"), base_gate + 0.05, None
        return True, Decimal("1.0"), base_gate, None

    return True, Decimal("1.0"), base_gate, None


def _cap_quantity_pct(
    *,
    quantity_pct: Decimal,
    wallet: Any,
    equity: Decimal,
    max_position_size_pct: Decimal,
) -> Decimal:
    if wallet.available_usdt <= 0:
        return Decimal("0")
    max_spend = equity * (max_position_size_pct / Decimal("100"))
    capped_pct = min(quantity_pct, max_spend / wallet.available_usdt)
    return max(capped_pct, Decimal("0"))


def _build_portfolio_risk_manager(strategy: Strategy, config: dict[str, Any]) -> PortfolioRiskManager:
    return PortfolioRiskManager(
        max_exposure_pct=float(config.get("portfolio_max_exposure_pct", 70.0)),
        max_single_asset_pct=float(config.get("portfolio_max_single_asset_pct", 40.0)),
        max_concurrent_positions=resolve_max_concurrent_positions(strategy),
        portfolio_drawdown_halt_pct=float(config.get("portfolio_drawdown_halt_pct", 20.0)),
    )


def _apply_portfolio_risk_limits(
    *,
    strategy: Strategy,
    config: dict[str, Any],
    wallet: Any,
    symbol: str,
    quantity_pct: Decimal,
    regime: MarketRegime,
    all_positions: list[Any],
) -> tuple[Decimal, str | None]:
    if quantity_pct <= Decimal("0"):
        return Decimal("0"), "Position size is zero after sizing"

    total_equity = compute_total_equity(wallet, all_positions)
    manager = _build_portfolio_risk_manager(strategy, config)
    decision = manager.evaluate(
        proposed_symbol=symbol,
        proposed_value=(Decimal(str(wallet.available_usdt)) * quantity_pct).quantize(Decimal("0.00000001")),
        proposed_quantity_pct=quantity_pct,
        total_portfolio_equity=total_equity,
        portfolio_peak_equity=Decimal(str(wallet.peak_equity_usdt or total_equity)),
        open_positions=build_portfolio_positions(all_positions, strategy_id=strategy.id),
        regime=regime,
    )
    if not decision.approved:
        return Decimal("0"), decision.reason

    adjusted = decision.adjusted_quantity_pct if decision.adjusted_quantity_pct is not None else quantity_pct
    warnings = f" ({'; '.join(decision.warnings)})" if decision.warnings else ""
    reason = None
    if adjusted != quantity_pct:
        reason = f"{decision.reason}{warnings}"
    return adjusted, reason


def _decision_reason(decision: LiveTradeDecision) -> str:
    if decision.validator_reason:
        return f"{decision.reason} | validator={decision.validator_reason}"
    return decision.reason


def _precompute_entry_levels(
    indicators: dict[str, Any],
    market_price: Decimal,
    config: dict[str, Any],
) -> tuple[Decimal, Decimal, Decimal] | None:
    atr_values = indicators.get("atr", [])
    if not atr_values:
        return None
    entry_atr = Decimal(str(atr_values[-1]))
    stop_loss, take_profit = calculate_exit_levels(
        entry_price=market_price,
        atr=entry_atr,
        atr_multiplier=Decimal(str(config.get("atr_stop_multiplier", 2.0))),
        take_profit_ratio=Decimal(str(config.get("take_profit_ratio", 2.0))),
    )
    return stop_loss, take_profit, entry_atr


def _build_validation_context(
    *,
    strategy: Strategy,
    symbol: str,
    interval: str,
    indicators: dict[str, Any],
    ai_config: dict[str, Any],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    closes: list[float],
    wallet: Any,
    position: Any,
    market_price: Decimal,
    decision: LiveTradeDecision,
    safety_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flat_metrics = analyze_flat_market(
        closes,
        ai_config.get("flat_market_threshold_pct", settings.ai_flat_market_threshold_pct),
        indicators.get("atr"),
    )[1]
    context = build_ai_context(
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
        has_position=position is not None,
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
        algorithmic_signal={
            "action": decision.action,
            "reason": decision.reason,
            "raw_confidence": round(decision.raw_confidence, 4),
            "final_confidence": round(decision.final_confidence, 4),
            "regime": decision.regime,
            **(
                {
                    "composite_score": round(decision.composite_result.composite_score, 4),
                    "direction": decision.composite_result.direction,
                    "votes": {k: round(v, 4) for k, v in decision.composite_result.votes.items()},
                }
                if decision.composite_result is not None
                else {}
            ),
        },
    )
    if safety_context:
        context["safety"] = safety_context
    return context


async def _apply_ai_validation(
    session: Any,
    strategy: Strategy,
    symbol: str,
    interval: str,
    indicators: dict[str, Any],
    ai_config: dict[str, Any],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    closes: list[float],
    wallet: Any,
    position: Any,
    market_price: Decimal,
    decision: LiveTradeDecision,
    force: bool,
    cycle_id: str | None = None,
    local_safety: SafetyVerdict | None = None,
) -> SafetyVerdict | LiveTradeDecision:
    legacy_mode = local_safety is None
    effective_cycle_id = cycle_id or str(uuid4())
    safety_verdict = local_safety or SafetyVerdict(
        status="approved",
        approved=True,
        reason_code=None,
        reason_text="Legacy AI validation path assumed deterministic safety pass",
        fatal_flags=[],
        evidence={},
    )
    if decision.action != "BUY":
        return decision if legacy_mode else safety_verdict
    if not ai_config["ai_enabled"]:
        return decision if legacy_mode else safety_verdict

    context = _build_validation_context(
        strategy=strategy,
        safety_context=safety_verdict.to_dict(),
        symbol=symbol,
        interval=interval,
        indicators=indicators,
        ai_config=ai_config,
        highs=highs,
        lows=lows,
        volumes=volumes,
        closes=closes,
        wallet=wallet,
        position=position,
        market_price=market_price,
        decision=decision,
    )
    validation = await evaluate_ai_validation(context=context, proposed_action=decision.action)

    if validation.usage is not None:
        _touch_ai_metrics(
            strategy,
            status=validation.status,
            reason=validation.reason or validation.error or validation.raw_response,
            usage=validation.usage,
        )
    else:
        strategy.ai_last_decision_status = validation.status
        strategy.ai_last_reasoning = validation.reason or validation.error

    session.add(
        _build_ai_validation_log(
            strategy.id,
            symbol,
            validation=validation,
            proposed_action=decision.action,
        )
    )
    ai_reason_code = validation.reason_code or AI_SAFETY_UNAVAILABLE
    ai_fatal_flags = list(validation.fatal_flags or [])
    if validation.status in {"error", "skipped"} or validation.approved is None:
        ai_fatal_flags.append(AI_SAFETY_UNAVAILABLE)
        verdict = SafetyVerdict(
            status="rejected",
            approved=False,
            reason_code=AI_SAFETY_UNAVAILABLE,
            reason_text=validation.error or validation.reason or "AI safety validation unavailable",
            fatal_flags=list(dict.fromkeys(ai_fatal_flags)),
            evidence={"validation": validation.evidence or {}, "local_safety": safety_verdict.to_dict()},
            usage=validation.usage,
            raw_response=validation.raw_response,
            error=validation.error,
        )
    elif not validation.approved:
        verdict = SafetyVerdict(
            status="rejected",
            approved=False,
            reason_code=ai_reason_code,
            reason_text=validation.reason or "AI safety validation rejected the trade",
            fatal_flags=list(dict.fromkeys(ai_fatal_flags or [ai_reason_code])),
            evidence={"validation": validation.evidence or {}, "local_safety": safety_verdict.to_dict()},
            usage=validation.usage,
            raw_response=validation.raw_response,
            error=validation.error,
        )
    else:
        verdict = SafetyVerdict(
            status="approved",
            approved=True,
            reason_code=validation.reason_code,
            reason_text=validation.reason or "AI safety validation approved the trade",
            fatal_flags=[],
            evidence={"validation": validation.evidence or {}, "local_safety": safety_verdict.to_dict()},
            usage=validation.usage,
            raw_response=validation.raw_response,
            error=validation.error,
        )

    _log_stage(
        session,
        strategy_id=strategy.id,
        cycle_id=effective_cycle_id,
        symbol=symbol,
        stage="ai_safety",
        status="passed" if verdict.approved else "rejected",
        reason_code=verdict.reason_code,
        reason_text=verdict.reason_text,
        metrics_json=verdict.evidence,
        context_json={"fatal_flags": verdict.fatal_flags},
    )
    if legacy_mode:
        if not verdict.approved:
            decision.final_confidence = 0.0
            decision.quantity_pct = Decimal("0")
            decision.validator_reason = verdict.error or verdict.reason_text
        if hasattr(session, "commit"):
            await commit_with_write_lock(session)
        return decision
    return verdict


async def _execute_shared_exit(
    session: Any,
    manager: ConnectionManager,
    strategy: Strategy,
    strategy_id: str,
    wallet: Any,
    position: Any,
    symbol: str,
    market_price: Decimal,
    quantity_pct: Decimal,
    reason: str,
    decision_source: str,
    indicators: dict[str, Any],
    *,
    composite_result: Any = None,
    exit_decision: Any = None,
) -> dict[str, Any]:
    result = await execute_sell(
        session,
        strategy_id,
        wallet,
        symbol,
        market_price,
        quantity_pct,
        reason=reason,
        strategy_name=strategy.name,
        strategy_type=(strategy.config_json or {}).get("strategy_type", "unknown"),
        decision_source=decision_source,
        indicator_snapshot=_build_indicator_snapshot(indicators),
        composite_score=(
            Decimal(str(round(composite_result.composite_score, 4)))
            if composite_result is not None
            else None
        ),
        composite_confidence=(
            Decimal(str(round(composite_result.confidence, 4)))
            if composite_result is not None
            else None
        ),
    )
    composite_dict = _serialize_composite_result(composite_result) if composite_result is not None else {}
    if result.success:
        if decision_source == "hybrid_exit" and quantity_pct >= Decimal("0.99999999"):
            _update_hybrid_calibration(strategy, position, result.trade)

        # Update scaled TP flags on remaining position after partial close
        if exit_decision is not None and getattr(exit_decision, "tp_level", None) is not None:
            remaining_pos = await get_position(session, strategy_id, symbol)
            if remaining_pos is not None:
                tp_level = exit_decision.tp_level
                if tp_level == 1:
                    remaining_pos.tp1_hit = True
                    # Move SL to breakeven on TP1
                    if exit_decision.updated_stop_loss_price is not None:
                        remaining_pos.stop_loss_price = exit_decision.updated_stop_loss_price
                elif tp_level == 2:
                    remaining_pos.tp2_hit = True

        await handle_post_trade(
            session,
            manager,
            result=result,
            strategy=strategy,
            strategy_id=strategy_id,
            wallet=wallet,
            symbol=symbol,
            market_price=market_price,
            action="SELL",
            reason=reason,
            decision_source=decision_source,
            is_sell=True,
            exit_decision=exit_decision,
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
            "reason": reason,
            "decision_source": decision_source,
            "composite": composite_dict,
        }

    await session.rollback()
    return {
        "status": "failed",
        "reason": result.error,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "decision_source": decision_source,
        "composite": composite_dict,
    }


def _build_indicator_snapshot(indicators: dict[str, Any]) -> dict[str, Any]:
    """Extract key indicator values for trade log context."""
    snap: dict[str, Any] = {}
    for key in ("rsi", "atr", "volume_ratio"):
        vals = indicators.get(key)
        if isinstance(vals, (list, tuple)) and vals:
            snap[key] = round(float(vals[-1]), 4)
        elif isinstance(vals, (int, float)):
            snap[key] = round(float(vals), 4)

    for key in ("sma_short", "sma_long", "ema_12", "ema_26"):
        vals = indicators.get(key)
        if isinstance(vals, (list, tuple)) and vals:
            snap[key] = round(float(vals[-1]), 2)

    macd_line, macd_signal, macd_hist = indicators.get("macd", ([], [], []))
    if isinstance(macd_line, (list, tuple)) and macd_line:
        snap["macd_line"] = round(float(macd_line[-1]), 4)
    if isinstance(macd_signal, (list, tuple)) and macd_signal:
        snap["macd_signal"] = round(float(macd_signal[-1]), 4)
    if isinstance(macd_hist, (list, tuple)) and macd_hist:
        snap["macd_histogram"] = round(float(macd_hist[-1]), 4)

    bb_upper, bb_middle, bb_lower = indicators.get("bollinger_bands", ([], [], []))
    for key, vals in (("bb_upper", bb_upper), ("bb_middle", bb_middle), ("bb_lower", bb_lower)):
        if isinstance(vals, (list, tuple)) and vals:
            snap[key] = round(float(vals[-1]), 2)

    return snap


INTERVAL_TO_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400,
}

# Per-strategy lock to prevent concurrent execution of run_single_cycle
_strategy_locks: dict[str, asyncio.Lock] = {}


async def run_single_cycle(
    strategy_id: str,
    symbol: str | None = None,
    interval: str | None = None,
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
        return await _run_single_cycle_locked(strategy_id, symbol, interval, force)


async def _run_single_cycle_locked(
    strategy_id: str,
    symbol: str | None = None,
    interval: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Execute one decision cycle for a strategy (must be called under lock)."""
    manager = ConnectionManager.get_instance()
    cycle_id = str(uuid4())
    async with SessionLocal() as session:
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

        resolved_interval = interval or strategy.candle_interval or (strategy.config_json or {}).get("candle_interval", settings.default_candle_interval)
        execution_mode = resolve_execution_mode(strategy)
        if execution_mode == MULTI_COIN_MODE:
            open_positions = await get_positions(session, strategy_id)
            open_position_symbols = {position.symbol for position in open_positions}
            await ensure_coordinated_picks_fresh(
                session,
                strategy,
                interval=resolved_interval,
                force_refresh=force,
                open_position_symbols=open_position_symbols,
                cycle_id=cycle_id,
            )
            result_payload = await _run_multi_coin_cycle(
                session,
                manager,
                strategy,
                strategy_id,
                resolved_interval,
                force,
                cycle_id,
            )
            await commit_with_write_lock(session)
            return result_payload

        resolved_symbol = str(symbol or resolve_primary_symbol(strategy)).upper()
        result_payload = await _run_loaded_symbol_cycle(
            session,
            manager,
            strategy,
            strategy_id,
            resolved_symbol,
            resolved_interval,
            force,
            cycle_id,
            entry_allowed=True,
        )
        await commit_with_write_lock(session)
        return result_payload

async def _run_loaded_symbol_cycle(
    session: Any,
    manager: ConnectionManager,
    strategy: Strategy,
    strategy_id: str,
    symbol: str,
    interval: str,
    force: bool,
    cycle_id: str,
    *,
    entry_allowed: bool,
) -> dict[str, Any]:
    store = DataStore.get_instance()
    candles = store.get_candles(symbol, interval)
    closes = [candle.close for candle in candles]
    if len(closes) < 50:
        logger.warning(
            "insufficient candles strategy_id=%s symbol=%s candles=%d required=50",
            strategy_id, symbol, len(closes),
        )
        return {
            "status": "skipped",
            "reason": "Not enough candle data",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "market_data",
        }

    config = strategy.config_json or {}
    strategy_type = config.get("strategy_type", "sma_crossover")
    if strategy_type == "ai":
        strategy_type = str(config.get("base_strategy_type", "sma_crossover"))
    ai_config = _normalize_ai_counters(strategy)

    wallet = await get_or_create_wallet(
        session,
        strategy_id,
        Decimal(str(config.get("initial_balance", 1000))),
    )
    position = await get_position(session, strategy_id, symbol)
    if position is None and not entry_allowed:
        return {
            "status": "skipped",
            "reason": "Symbol not eligible for new entries this cycle",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "daily_pick_filter",
        }

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
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    volumes = [candle.volume for candle in candles]
    indicators = compute_indicators(closes, config, highs=highs, lows=lows, volumes=volumes)
    indicators["symbol"] = symbol
    quote_volumes = [close * volume for close, volume in zip(closes[-24:], volumes[-24:])]
    tradability_result = evaluate_symbol_tradability(
        symbol=symbol,
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        volume_24h_usdt=sum(quote_volumes),
        config=config,
        indicators=indicators,
    )
    indicators["market_quality_score"] = tradability_result.market_quality_score
    entry_movement_quality = evaluate_movement_quality(direction="BUY", metrics=tradability_result.metrics, config=config)
    indicators["movement_quality_score"] = entry_movement_quality.score
    indicators["movement_quality"] = entry_movement_quality.to_dict()
    all_positions = await get_positions(session, strategy_id)
    equity = compute_total_equity(wallet, all_positions)
    has_position = position is not None
    regime_result, regime_transition = _regime_classifier.classify_with_transition(
        indicators, symbol=symbol,
    )
    logger.debug(
        "regime detected strategy_id=%s symbol=%s regime=%s confidence=%.2f transition=%s",
        strategy_id,
        symbol,
        regime_result.regime.value,
        regime_result.confidence,
        f"{regime_transition.from_regime.value}->{regime_transition.to_regime.value}" if regime_transition else "none",
    )

    # React to dangerous regime transitions
    if regime_transition is not None and regime_transition.is_dangerous and position is not None:
        logger.warning(
            "Dangerous regime transition %s->%s for %s, forcing exit",
            regime_transition.from_regime.value,
            regime_transition.to_regime.value,
            symbol,
        )
        return await _execute_shared_exit(
            session,
            manager,
            strategy,
            strategy_id,
            wallet,
            position,
            symbol,
            market_price,
            Decimal("1.0"),
            f"Regime transition {regime_transition.from_regime.value}->{regime_transition.to_regime.value} — forced exit",
            "regime_exit",
            indicators,
        )

    if position is None and entry_allowed:
        _log_stage(
            session,
            strategy_id=strategy_id,
            cycle_id=cycle_id,
            symbol=symbol,
            stage="entry_tradability",
            status="passed" if tradability_result.passed else "rejected",
            reason_code=_first_reason_code(tradability_result.reason_codes),
            reason_text=tradability_result.reason_text,
            metrics_json=tradability_result.metrics.to_dict(),
            context_json={"market_quality_score": tradability_result.market_quality_score},
        )
        if not tradability_result.passed:
            return {
                "status": "skipped",
                "reason": tradability_result.reason_text,
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "entry_tradability",
            }

    if strategy_type == "hybrid_composite":
        return await _run_hybrid_cycle(
            session, manager, strategy, strategy_id, wallet, position,
            symbol, interval, market_price, equity, indicators,
            config, ai_config, highs, lows, volumes, closes, force, regime_result,
            all_positions, cycle_id, tradability_result,
        )

    return await _run_rule_based_cycle(
        session, manager, strategy, strategy_id, wallet, position,
        symbol, interval, market_price, equity, indicators,
        config, ai_config, highs, lows, volumes, closes, force,
        strategy_type, has_position, regime_result, all_positions, cycle_id, tradability_result,
    )


def _summarize_multicoin_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "executed": 0,
        "buy_executed": 0,
        "sell_executed": 0,
        "hold": 0,
        "skipped": 0,
        "failed": 0,
    }
    for item in results:
        status = item.get("status")
        action = item.get("action")
        if status == "executed":
            summary["executed"] += 1
            if action == "BUY":
                summary["buy_executed"] += 1
            elif action == "SELL":
                summary["sell_executed"] += 1
        elif status == "hold":
            summary["hold"] += 1
        elif status == "failed":
            summary["failed"] += 1
        else:
            summary["skipped"] += 1
    return summary


async def _run_multi_coin_cycle(
    session: Any,
    manager: ConnectionManager,
    strategy: Strategy,
    strategy_id: str,
    interval: str,
    force: bool,
    cycle_id: str,
) -> dict[str, Any]:
    # Gather open position symbols for position-aware retention
    open_positions = await get_positions(session, strategy_id)
    open_position_symbols = {p.symbol for p in open_positions}

    picks = await ensure_daily_picks(
        session, strategy, interval=interval, force_refresh=False,
        open_position_symbols=open_position_symbols,
        cycle_id=cycle_id,
    )
    selection_date = picks[0].selection_date.isoformat() if picks else datetime.now(timezone.utc).date().isoformat()
    selected_symbols = [pick.symbol for pick in picks]
    if not selected_symbols:
        return {
            "status": "skipped",
            "reason": "No daily picks available",
            "strategy_id": strategy_id,
            "execution_mode": MULTI_COIN_MODE,
            "selection_date": selection_date,
            "selected_symbols": [],
            "results": [],
        }

    results: list[dict[str, Any]] = []
    open_positions = await get_positions(session, strategy_id)
    open_symbols = [position.symbol for position in open_positions]
    processed_symbols: set[str] = set()

    for symbol in open_symbols:
        result = await _run_loaded_symbol_cycle(
            session,
            manager,
            strategy,
            strategy_id,
            symbol,
            interval,
            force,
            cycle_id,
            entry_allowed=False,
        )
        await commit_with_write_lock(session)
        results.append(result)
        processed_symbols.add(symbol)

    max_positions = resolve_max_concurrent_positions(strategy)
    for pick in picks:
        if pick.symbol in processed_symbols:
            continue
        open_positions = await get_positions(session, strategy_id)
        if len(open_positions) >= max_positions:
            break
        result = await _run_loaded_symbol_cycle(
            session,
            manager,
            strategy,
            strategy_id,
            pick.symbol,
            interval,
            force,
            cycle_id,
            entry_allowed=True,
        )
        await commit_with_write_lock(session)
        results.append(result)
        processed_symbols.add(pick.symbol)

    return {
        "status": "completed",
        "strategy_id": strategy_id,
        "execution_mode": MULTI_COIN_MODE,
        "selection_date": selection_date,
        "selected_symbols": selected_symbols,
        "results": results,
        "summary": _summarize_multicoin_results(results),
    }


async def _run_hybrid_cycle(
    session: Any,
    manager: ConnectionManager,
    strategy: Strategy,
    strategy_id: str,
    wallet: Any,
    position: Any,
    symbol: str,
    interval: str,
    market_price: Decimal,
    equity: Decimal,
    indicators: dict[str, Any],
    config: dict[str, Any],
    ai_config: dict[str, Any],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    closes: list[float],
    force: bool,
    regime_result: RegimeResult,
    all_positions: list[Any],
    cycle_id: str,
    tradability_result: TradabilityResult,
) -> dict[str, Any]:
    """Execute the deterministic hybrid path with shared validation and exits."""
    strategy_type = "hybrid_composite"
    has_position = position is not None

    ctx = StrategyContext(
        symbol=symbol,
        interval=interval,
        market_price=market_price,
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        has_position=has_position,
        position=position,
        wallet=wallet,
        equity=equity,
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        strategy_type=strategy_type,
        config=config,
        ai_config=ai_config,
        regime=regime_result.regime.value,
        market_quality_score=tradability_result.market_quality_score,
        movement_quality_score=float(indicators.get("movement_quality_score", 0.0)),
        risk_per_trade_pct=Decimal(str(strategy.risk_per_trade_pct)),
        max_position_size_pct=Decimal(str(strategy.max_position_size_pct)),
        stop_loss_pct=Decimal(str(strategy.stop_loss_pct or settings.default_stop_loss_pct)),
        consecutive_losses=strategy.consecutive_losses,
        force=force,
    )

    hybrid_strategy = HybridCompositeStrategy()
    decision: HybridDecision = await hybrid_strategy.decide_hybrid_async(indicators, ctx)

    composite_dict = (
        _serialize_composite_result(decision.composite_result)
        if decision.composite_result
        else {}
    )

    # Handle exit decisions
    if decision.decision_source == "hybrid_exit" and decision.signal is not None:
        return await _execute_shared_exit(
            session,
            manager,
            strategy,
            strategy_id,
            wallet,
            position,
            symbol,
            market_price,
            decision.signal.quantity_pct,
            reason=decision.signal.reason,
            decision_source="hybrid_exit",
            indicators=indicators,
            composite_result=decision.composite_result,
            exit_decision=decision.exit_decision,
        )

    # Handle trailing stop update (hold with trailing stop change)
    if (
        decision.decision_source == "hybrid_exit"
        and decision.exit_decision is not None
        and decision.exit_decision.updated_trailing_stop_price is not None
    ):
        if position is not None:
            hybrid_updated = False
            prior = position.trailing_stop_price
            new_ts = decision.exit_decision.updated_trailing_stop_price
            if new_ts != prior:
                position.trailing_stop_price = new_ts
                hybrid_updated = True
            new_sl = decision.exit_decision.updated_stop_loss_price
            if new_sl is not None and new_sl != position.stop_loss_price:
                position.stop_loss_price = new_sl
                hybrid_updated = True
            if hybrid_updated:
                await commit_with_write_lock(session)
                return {
                    "status": "hold",
                    "reason": "Exit levels updated (trailing/breakeven)",
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "decision_source": "hybrid_exit",
                    "composite": composite_dict,
                }

    logger.info(
        "hybrid_decision strategy_id=%s symbol=%s status=%s reason=%s raw_confidence=%s composite_score=%s",
        strategy_id, symbol, decision.status, decision.reason,
        decision.raw_confidence,
        decision.composite_result.composite_score if decision.composite_result else None,
    )
    if decision.status != "candidate" or decision.composite_result is None or decision.raw_confidence is None:
        if decision.composite_result is not None:
            _log_stage(
                session,
                strategy_id=strategy_id,
                cycle_id=cycle_id,
                symbol=symbol,
                stage="composite",
                status="rejected",
                reason_code=_first_reason_code(getattr(decision.composite_result, "reject_reason_codes", [])),
                reason_text=decision.reason,
                metrics_json=_serialize_composite_result(decision.composite_result),
                context_json={"status": decision.status},
            )
        return {
            "status": decision.status,
            "reason": decision.reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": decision.decision_source,
            "composite": composite_dict,
        }

    raw_confidence = _clamp_confidence(decision.raw_confidence)
    entry_bucket = _confidence_bucket(raw_confidence)
    calibration_multiplier = _hybrid_calibration_multiplier(config, entry_bucket)
    live_decision = LiveTradeDecision(
        action="BUY",
        reason=decision.reason,
        raw_confidence=raw_confidence,
        final_confidence=_clamp_confidence(raw_confidence * calibration_multiplier),
        regime=regime_result.regime.value,
        decision_source="hybrid_entry",
        composite_result=decision.composite_result,
        entry_confidence_bucket=entry_bucket,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="composite",
        status="passed" if not decision.composite_result.reject_reason_codes else "rejected",
        reason_code=_first_reason_code(decision.composite_result.reject_reason_codes),
        reason_text=decision.reason,
        metrics_json=_serialize_composite_result(decision.composite_result),
        context_json={"raw_confidence": raw_confidence},
    )
    if decision.composite_result.reject_reason_codes:
        return {
            "status": "skipped",
            "reason": decision.reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "composite",
            "composite": composite_dict,
        }

    # Re-entry cooldown after stop-loss
    cooldown_ok, cooldown_reason = _check_reentry_cooldown(strategy, symbol, interval)
    if not cooldown_ok:
        _log_stage(
            session,
            strategy_id=strategy_id,
            cycle_id=cycle_id,
            symbol=symbol,
            stage="reentry_cooldown",
            status="rejected",
            reason_code="REENTRY_COOLDOWN_ACTIVE",
            reason_text=cooldown_reason,
        )
        return {
            "status": "skipped",
            "reason": cooldown_reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "reentry_cooldown",
            "composite": composite_dict,
        }

    risk_reason = _entry_risk_status(strategy, wallet, equity, config)
    if risk_reason is not None:
        await commit_with_write_lock(session)
        return {
            "status": "halted",
            "reason": risk_reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "risk",
            "composite": composite_dict,
        }

    base_gate = _base_entry_gate(strategy_type, config)
    allowed, size_multiplier, min_confidence, regime_reason = _regime_entry_policy(
        strategy_type,
        regime_result.regime,
        base_gate,
    )
    logger.info(
        "regime_entry_policy strategy_id=%s symbol=%s regime=%s strategy_type=%s allowed=%s size_mult=%s gate=%.3f reason=%s",
        strategy_id, symbol, regime_result.regime.value, strategy_type,
        allowed, size_multiplier, min_confidence, regime_reason,
    )
    if not allowed:
        return {
            "status": "skipped",
            "reason": regime_reason or "Regime gate blocked entry",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "regime",
            "composite": composite_dict,
        }

    # Multi-timeframe confluence check
    mtf = check_confluence(symbol, "BUY", interval)
    logger.info(
        "mtf_confluence strategy_id=%s symbol=%s aligned=%s trend=%s boost=%.3f reason=%s",
        strategy_id, symbol, mtf.aligned, mtf.htf_trend, mtf.confidence_boost, mtf.reason,
    )
    if not mtf.aligned:
        return {
            "status": "skipped",
            "reason": mtf.reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "mtf_confluence",
            "composite": composite_dict,
        }
    live_decision.final_confidence = max(
        0.0, min(live_decision.final_confidence + mtf.confidence_boost, 1.0)
    )
    if live_decision.final_confidence < min_confidence:
        return {
            "status": "skipped",
            "reason": f"Hybrid confidence {live_decision.final_confidence:.3f} below gate {min_confidence:.3f}",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "confidence_gate",
            "composite": composite_dict,
        }

    entry_levels = _precompute_entry_levels(indicators, market_price, config)
    if entry_levels is None:
        return {
            "status": "skipped",
            "reason": "ATR unavailable for economic viability",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "economic_viability",
            "composite": composite_dict,
        }
    stop_loss_price, take_profit_price, _ = entry_levels
    estimated_notional = min(
        Decimal(str(wallet.available_usdt)),
        equity * (Decimal(str(strategy.max_position_size_pct)) / Decimal("100")),
    )
    economic_viability = evaluate_economic_viability(
        entry_price=market_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        notional=estimated_notional,
        config=config,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="economic_viability",
        status="passed" if economic_viability.passed else "rejected",
        reason_code=_first_reason_code(economic_viability.reason_codes),
        reason_text=economic_viability.reason_text,
        metrics_json=economic_viability.to_dict(),
        context_json={"estimated_notional": float(estimated_notional)},
    )
    if not economic_viability.passed:
        return {
            "status": "skipped",
            "reason": economic_viability.reason_text,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "economic_viability",
            "composite": composite_dict,
        }

    movement_quality = evaluate_movement_quality(direction="BUY", metrics=tradability_result.metrics, config=config)
    local_safety = evaluate_local_trade_safety(
        tradability=tradability_result,
        movement_quality=movement_quality,
        economic_viability=economic_viability,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="local_safety",
        status="passed" if local_safety.approved else "rejected",
        reason_code=local_safety.reason_code,
        reason_text=local_safety.reason_text,
        metrics_json=local_safety.evidence,
        context_json={"fatal_flags": local_safety.fatal_flags},
    )
    if not local_safety.approved:
        return {
            "status": "skipped",
            "reason": local_safety.reason_text,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "local_safety",
            "composite": composite_dict,
        }

    ai_safety = await _apply_ai_validation(
        session=session,
        strategy=strategy,
        symbol=symbol,
        interval=interval,
        indicators=indicators,
        ai_config=ai_config,
        highs=highs,
        lows=lows,
        volumes=volumes,
        closes=closes,
        wallet=wallet,
        position=position,
        market_price=market_price,
        decision=live_decision,
        force=force,
        cycle_id=cycle_id,
        local_safety=local_safety,
    )
    if not ai_safety.approved:
        live_decision.final_confidence = 0.0
        live_decision.validator_reason = ai_safety.reason_text

    sizing_result = hybrid_strategy.compute_sizing(indicators, ctx, live_decision.final_confidence)
    if sizing_result is None:
        return {
            "status": "skipped",
            "reason": "ATR unavailable or sizing produced zero",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "hybrid_entry",
            "composite": composite_dict,
        }
    sizing, skip_reason = sizing_result
    if skip_reason:
        return {
            "status": "skipped",
            "reason": skip_reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "hybrid_entry",
            "composite": composite_dict,
        }

    sizing_safety = evaluate_position_sizing_safety(
        entry_price=market_price,
        sizing=sizing,
        total_round_trip_cost_pct=Decimal(str(economic_viability.total_round_trip_cost_pct)),
        config=config,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="position_sizing",
        status="passed" if sizing_safety.passed else "rejected",
        reason_code=sizing_safety.reason_code,
        reason_text=sizing_safety.reason_text,
        metrics_json={
            "atr_pct": float(sizing_safety.atr_pct),
            "stop_distance_pct": float(sizing_safety.stop_distance_pct),
            "take_profit_distance_pct": float(sizing_safety.take_profit_distance_pct),
            "min_atr_pct": float(sizing_safety.min_atr_pct),
            "min_stop_distance_pct": float(sizing_safety.min_stop_distance_pct),
            "min_take_profit_distance_pct": float(sizing_safety.min_take_profit_distance_pct),
        },
        context_json={"quantity_pct": float(sizing.quantity_pct)},
    )

    quantity_pct = sizing.quantity_pct * size_multiplier
    quantity_pct = _cap_quantity_pct(
        quantity_pct=quantity_pct,
        wallet=wallet,
        equity=equity,
        max_position_size_pct=Decimal(str(strategy.max_position_size_pct)),
    )
    if quantity_pct <= Decimal("0"):
        return {
            "status": "skipped",
            "reason": "Hybrid sizing produced zero quantity after caps",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "hybrid_entry",
            "composite": composite_dict,
        }

    quantity_pct, risk_reason = _apply_portfolio_risk_limits(
        strategy=strategy,
        config=config,
        wallet=wallet,
        symbol=symbol,
        quantity_pct=quantity_pct,
        regime=regime_result.regime,
        all_positions=all_positions,
    )
    if quantity_pct <= Decimal("0"):
        return {
            "status": "skipped",
            "reason": risk_reason or "Portfolio risk blocked entry",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "portfolio_risk",
            "composite": composite_dict,
        }

    live_decision.quantity_pct = quantity_pct
    execution_readiness = _build_execution_readiness(
        tradability=tradability_result,
        signal_quality_passed=not decision.composite_result.reject_reason_codes,
        economic_viability=economic_viability,
        ai_safety=ai_safety,
        sizing_safety=sizing_safety,
    )
    if (
        not execution_readiness.tradability_passed
        or not execution_readiness.signal_quality_passed
        or not execution_readiness.economic_viability_passed
        or not execution_readiness.ai_safety_passed
        or not execution_readiness.sizing_passed
        or execution_readiness.fatal_flags
    ):
        _log_stage(
            session,
            strategy_id=strategy_id,
            cycle_id=cycle_id,
            symbol=symbol,
            stage="final_execution",
            status="rejected",
            reason_code=_first_reason_code(execution_readiness.reason_codes),
            reason_text=execution_readiness.reason_text,
            metrics_json=execution_readiness.metrics,
            context_json={"fatal_flags": execution_readiness.fatal_flags},
        )
        return {
            "status": "skipped",
            "reason": execution_readiness.reason_text,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "final_execution",
            "composite": composite_dict,
        }

    result = await execute_buy(
        session,
        strategy_id,
        wallet,
        symbol,
        market_price,
        quantity_pct,
        reason=_decision_reason(live_decision),
        strategy_name=strategy.name,
        strategy_type=strategy_type,
        decision_source="hybrid_entry",
        indicator_snapshot=_build_indicator_snapshot(indicators),
        composite_score=Decimal(str(round(decision.composite_result.composite_score, 4))),
        composite_confidence=Decimal(str(round(live_decision.final_confidence, 4))),
        entry_confidence_raw=Decimal(str(round(live_decision.raw_confidence, 4))),
        entry_confidence_final=Decimal(str(round(live_decision.final_confidence, 4))),
        entry_confidence_bucket=entry_bucket,
    )
    if not result.success:
        await session.rollback()
        return {
            "status": "failed",
            "reason": result.error,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "decision_source": "hybrid_entry",
            "composite": composite_dict,
        }

    refreshed_position = await get_position(session, strategy_id, symbol)
    if refreshed_position is not None:
        refreshed_position.stop_loss_price = sizing.stop_loss_price
        refreshed_position.take_profit_price = sizing.take_profit_price
        refreshed_position.trailing_stop_price = None
        refreshed_position.entry_atr = sizing.entry_atr
        refreshed_position.entry_confidence_raw = Decimal(str(round(live_decision.raw_confidence, 4)))
        refreshed_position.entry_confidence_final = Decimal(str(round(live_decision.final_confidence, 4)))
        refreshed_position.entry_confidence_bucket = entry_bucket
        # Scaled take-profit levels
        scaled = calculate_scaled_exit_levels(
            entry_price=market_price,
            atr=sizing.entry_atr,
            atr_multiplier=Decimal(str(config.get("atr_stop_multiplier", 2.0))),
        )
        refreshed_position.take_profit_1_price = scaled.take_profit_1_price
        refreshed_position.take_profit_2_price = scaled.take_profit_2_price
        refreshed_position.take_profit_3_price = scaled.take_profit_3_price
        refreshed_position.tp1_hit = False
        refreshed_position.tp2_hit = False

    await handle_post_trade(
        session,
        manager,
        result=result,
        strategy=strategy,
        strategy_id=strategy_id,
        wallet=wallet,
        symbol=symbol,
        market_price=market_price,
        action="BUY",
        reason=_decision_reason(live_decision),
        decision_source="hybrid_entry",
        is_sell=False,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="final_execution",
        status="passed",
        reason_code=None,
        reason_text="Trade executed after final sanity check",
        metrics_json=execution_readiness.metrics,
        context_json={"fatal_flags": execution_readiness.fatal_flags, "trade_id": result.trade.id},
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
        "reason": _decision_reason(live_decision),
        "decision_source": "hybrid_entry",
        "composite": composite_dict,
        "signal": _serialize_signal_result({
            "action": "BUY",
            "symbol": symbol,
            "quantity_pct": quantity_pct,
            "reason": _decision_reason(live_decision),
        }),
    }


def _signal_to_confidence_tier(signal_quantity_pct: Decimal) -> str:
    """Map a rule-based strategy's quantity_pct hint to a confidence tier."""
    pct = float(signal_quantity_pct)
    if pct >= 0.5:
        return "full"
    if pct >= 0.3:
        return "reduced"
    return "small"


async def _run_rule_based_cycle(
    session: Any,
    manager: ConnectionManager,
    strategy: Strategy,
    strategy_id: str,
    wallet: Any,
    position: Any,
    symbol: str,
    interval: str,
    market_price: Decimal,
    equity: Decimal,
    indicators: dict[str, Any],
    config: dict[str, Any],
    ai_config: dict[str, Any],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    closes: list[float],
    force: bool,
    strategy_type: str,
    has_position: bool,
    regime_result: RegimeResult,
    all_positions: list[Any],
    cycle_id: str,
    tradability_result: TradabilityResult,
) -> dict[str, Any]:
    """Execute deterministic rule strategies with shared exits and validation."""
    strategy_impl = get_strategy_class(strategy_type)()

    if position is not None:
        exit_decision = evaluate_exit(
            position=position,
            current_price=market_price,
            composite_score=None,
            config=config,
            now=datetime.now(timezone.utc),
            regime=regime_result.regime.value,
        )
        if exit_decision.action == "SELL":
            return await _execute_shared_exit(
                session,
                manager,
                strategy,
                strategy_id,
                wallet,
                position,
                symbol,
                market_price,
                exit_decision.quantity_pct,
                exit_decision.reason,
                "rule_exit",
                indicators,
                exit_decision=exit_decision,
            )

        updated = False
        if (
            exit_decision.updated_trailing_stop_price is not None
            and exit_decision.updated_trailing_stop_price != position.trailing_stop_price
        ):
            position.trailing_stop_price = exit_decision.updated_trailing_stop_price
            updated = True
        if (
            exit_decision.updated_stop_loss_price is not None
            and exit_decision.updated_stop_loss_price != position.stop_loss_price
        ):
            position.stop_loss_price = exit_decision.updated_stop_loss_price
            updated = True
        if updated:
            await commit_with_write_lock(session)
            return {
                "status": "hold",
                "reason": "Exit levels updated (trailing/breakeven)",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "decision_source": "rule_exit",
            }

        signal = strategy_impl.decide(indicators, True, wallet.available_usdt)
        if signal is not None and signal.action.value == "SELL":
            return await _execute_shared_exit(
                session,
                manager,
                strategy,
                strategy_id,
                wallet,
                position,
                symbol,
                market_price,
                signal.quantity_pct,
                signal.reason,
                "rule_exit",
                indicators,
            )
        return {
            "status": "hold",
            "reason": "Position open; no shared exit signal",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "rule_exit",
        }

    signal = strategy_impl.decide(indicators, has_position, wallet.available_usdt)
    logger.info(
        "rule_entry decide result strategy_id=%s symbol=%s strategy_type=%s signal=%s",
        strategy_id, symbol, strategy_type,
        f"{signal.action.value} qty={signal.quantity_pct}" if signal else "None",
    )
    if signal is None or signal.action.value != "BUY":
        return {
            "status": "hold",
            "reason": "No trade signal",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "rule_entry",
        }

    atr_values = indicators.get("atr", [])
    if not atr_values:
        return {
            "status": "skipped",
            "reason": "ATR unavailable for position sizing",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "rule_entry",
        }

    confidence_tier = _signal_to_confidence_tier(signal.quantity_pct)
    sizing = calculate_position_size(
        equity=equity,
        entry_price=market_price,
        atr=Decimal(str(atr_values[-1])),
        atr_multiplier=Decimal(str(config.get("atr_stop_multiplier", 2.0))),
        risk_per_trade_pct=Decimal(str(strategy.risk_per_trade_pct or settings.default_risk_per_trade_pct)),
        confidence_tier=confidence_tier,
        losing_streak_count=int(strategy.consecutive_losses or 0),
        max_position_pct=Decimal(str(strategy.max_position_size_pct or settings.default_max_position_size_pct)),
        take_profit_ratio=Decimal(str(config.get("take_profit_ratio", 2.0))),
    )
    if sizing.quantity_pct <= Decimal("0"):
        return {
            "status": "skipped",
            "reason": "ATR-based sizing produced zero position",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "rule_entry",
        }
    stop_loss_price = sizing.stop_loss_price
    take_profit_price = sizing.take_profit_price
    entry_atr = sizing.entry_atr

    raw_confidence = float(sizing.quantity_pct)
    live_decision = LiveTradeDecision(
        action="BUY",
        reason=signal.reason,
        raw_confidence=raw_confidence,
        final_confidence=raw_confidence,
        regime=regime_result.regime.value,
        quantity_pct=sizing.quantity_pct,
        decision_source="rule_entry",
        entry_confidence_bucket=_confidence_bucket(raw_confidence),
    )

    # Re-entry cooldown after stop-loss
    cooldown_ok, cooldown_reason = _check_reentry_cooldown(strategy, symbol, interval)
    if not cooldown_ok:
        _log_stage(
            session,
            strategy_id=strategy_id,
            cycle_id=cycle_id,
            symbol=symbol,
            stage="reentry_cooldown",
            status="rejected",
            reason_code="REENTRY_COOLDOWN_ACTIVE",
            reason_text=cooldown_reason,
        )
        return {
            "status": "skipped",
            "reason": cooldown_reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "reentry_cooldown",
        }

    risk_reason = _entry_risk_status(strategy, wallet, equity, config)
    if risk_reason is not None:
        await commit_with_write_lock(session)
        return {
            "status": "halted",
            "reason": risk_reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "risk",
        }

    base_gate = _base_entry_gate(strategy_type, config)
    allowed, size_multiplier, min_confidence, regime_reason = _regime_entry_policy(
        strategy_type,
        regime_result.regime,
        base_gate,
    )
    logger.info(
        "regime_entry_policy strategy_id=%s symbol=%s regime=%s strategy_type=%s allowed=%s size_mult=%s gate=%.3f reason=%s",
        strategy_id, symbol, regime_result.regime.value, strategy_type,
        allowed, size_multiplier, min_confidence, regime_reason,
    )
    if not allowed:
        return {
            "status": "skipped",
            "reason": regime_reason or "Regime gate blocked entry",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "regime",
        }
    live_decision.quantity_pct *= size_multiplier

    # Multi-timeframe confluence check
    mtf = check_confluence(symbol, "BUY", interval)
    logger.info(
        "mtf_confluence strategy_id=%s symbol=%s aligned=%s trend=%s boost=%.3f reason=%s",
        strategy_id, symbol, mtf.aligned, mtf.htf_trend, mtf.confidence_boost, mtf.reason,
    )
    if not mtf.aligned:
        return {
            "status": "skipped",
            "reason": mtf.reason,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "mtf_confluence",
        }
    live_decision.final_confidence = max(
        0.0, min(live_decision.final_confidence + mtf.confidence_boost, 1.0)
    )
    if live_decision.final_confidence < min_confidence:
        return {
            "status": "skipped",
            "reason": f"Entry confidence {live_decision.final_confidence:.3f} below gate {min_confidence:.3f}",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "confidence_gate",
        }

    economic_viability = evaluate_economic_viability(
        entry_price=market_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        notional=min(
            Decimal(str(wallet.available_usdt)),
            equity * (Decimal(str(strategy.max_position_size_pct)) / Decimal("100")),
        ),
        config=config,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="economic_viability",
        status="passed" if economic_viability.passed else "rejected",
        reason_code=_first_reason_code(economic_viability.reason_codes),
        reason_text=economic_viability.reason_text,
        metrics_json=economic_viability.to_dict(),
        context_json={"strategy_type": strategy_type},
    )
    logger.info(
        "economic_viability strategy_id=%s symbol=%s passed=%s reason=%s",
        strategy_id, symbol, economic_viability.passed, economic_viability.reason_text,
    )
    if not economic_viability.passed:
        return {
            "status": "skipped",
            "reason": economic_viability.reason_text,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "economic_viability",
        }

    movement_quality = evaluate_movement_quality(direction="BUY", metrics=tradability_result.metrics, config=config)
    local_safety = evaluate_local_trade_safety(
        tradability=tradability_result,
        movement_quality=movement_quality,
        economic_viability=economic_viability,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="local_safety",
        status="passed" if local_safety.approved else "rejected",
        reason_code=local_safety.reason_code,
        reason_text=local_safety.reason_text,
        metrics_json=local_safety.evidence,
        context_json={"fatal_flags": local_safety.fatal_flags},
    )
    if not local_safety.approved:
        return {
            "status": "skipped",
            "reason": local_safety.reason_text,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "local_safety",
        }

    ai_safety = await _apply_ai_validation(
        session=session,
        strategy=strategy,
        symbol=symbol,
        interval=interval,
        indicators=indicators,
        ai_config=ai_config,
        highs=highs,
        lows=lows,
        volumes=volumes,
        closes=closes,
        wallet=wallet,
        position=position,
        market_price=market_price,
        decision=live_decision,
        force=force,
        cycle_id=cycle_id,
        local_safety=local_safety,
    )
    if not ai_safety.approved:
        live_decision.final_confidence = 0.0
        live_decision.validator_reason = ai_safety.reason_text

    quantity_pct = _cap_quantity_pct(
        quantity_pct=live_decision.quantity_pct,
        wallet=wallet,
        equity=equity,
        max_position_size_pct=Decimal(str(strategy.max_position_size_pct)),
    )
    if quantity_pct <= Decimal("0"):
        return {
            "status": "skipped",
            "reason": "Position size capped to zero",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "risk",
        }

    quantity_pct, risk_reason = _apply_portfolio_risk_limits(
        strategy=strategy,
        config=config,
        wallet=wallet,
        symbol=symbol,
        quantity_pct=quantity_pct,
        regime=regime_result.regime,
        all_positions=all_positions,
    )
    if quantity_pct <= Decimal("0"):
        return {
            "status": "skipped",
            "reason": risk_reason or "Portfolio risk blocked entry",
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "portfolio_risk",
        }

    live_decision.quantity_pct = quantity_pct
    sizing_safety = evaluate_position_sizing_safety(
        entry_price=market_price,
        sizing=sizing,
        total_round_trip_cost_pct=Decimal(str(economic_viability.total_round_trip_cost_pct)),
        config=config,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="position_sizing",
        status="passed" if sizing_safety.passed else "rejected",
        reason_code=sizing_safety.reason_code,
        reason_text=sizing_safety.reason_text,
        metrics_json={
            "atr_pct": float(sizing_safety.atr_pct),
            "stop_distance_pct": float(sizing_safety.stop_distance_pct),
            "take_profit_distance_pct": float(sizing_safety.take_profit_distance_pct),
            "min_atr_pct": float(sizing_safety.min_atr_pct),
            "min_stop_distance_pct": float(sizing_safety.min_stop_distance_pct),
            "min_take_profit_distance_pct": float(sizing_safety.min_take_profit_distance_pct),
        },
        context_json={"quantity_pct": float(quantity_pct)},
    )
    execution_readiness = _build_execution_readiness(
        tradability=tradability_result,
        signal_quality_passed=True,
        economic_viability=economic_viability,
        ai_safety=ai_safety,
        sizing_safety=sizing_safety,
    )
    if (
        not execution_readiness.tradability_passed
        or not execution_readiness.signal_quality_passed
        or not execution_readiness.economic_viability_passed
        or not execution_readiness.ai_safety_passed
        or not execution_readiness.sizing_passed
        or execution_readiness.fatal_flags
    ):
        _log_stage(
            session,
            strategy_id=strategy_id,
            cycle_id=cycle_id,
            symbol=symbol,
            stage="final_execution",
            status="rejected",
            reason_code=_first_reason_code(execution_readiness.reason_codes),
            reason_text=execution_readiness.reason_text,
            metrics_json=execution_readiness.metrics,
            context_json={"fatal_flags": execution_readiness.fatal_flags},
        )
        return {
            "status": "skipped",
            "reason": execution_readiness.reason_text,
            "symbol": symbol,
            "strategy_id": strategy_id,
            "decision_source": "final_execution",
        }

    entry_confidence_bucket = _confidence_bucket(live_decision.final_confidence)
    result = await execute_buy(
        session,
        strategy_id,
        wallet,
        symbol,
        market_price,
        quantity_pct,
        reason=_decision_reason(live_decision),
        strategy_name=strategy.name,
        strategy_type=strategy_type,
        decision_source="rule_entry",
        indicator_snapshot=_build_indicator_snapshot(indicators),
        entry_confidence_raw=Decimal(str(round(live_decision.raw_confidence, 4))),
        entry_confidence_final=Decimal(str(round(live_decision.final_confidence, 4))),
        entry_confidence_bucket=entry_confidence_bucket,
    )
    if not result.success:
        await session.rollback()
        return {
            "status": "failed",
            "reason": result.error,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "decision_source": "rule_entry",
        }

    refreshed_position = await get_position(session, strategy_id, symbol)
    if refreshed_position is not None:
        refreshed_position.stop_loss_price = stop_loss_price
        refreshed_position.take_profit_price = take_profit_price
        refreshed_position.trailing_stop_price = None
        refreshed_position.entry_atr = entry_atr
        # Scaled take-profit levels
        scaled = calculate_scaled_exit_levels(
            entry_price=market_price,
            atr=entry_atr,
            atr_multiplier=Decimal(str(config.get("atr_stop_multiplier", 2.0))),
        )
        refreshed_position.take_profit_1_price = scaled.take_profit_1_price
        refreshed_position.take_profit_2_price = scaled.take_profit_2_price
        refreshed_position.take_profit_3_price = scaled.take_profit_3_price
        refreshed_position.tp1_hit = False
        refreshed_position.tp2_hit = False

    await handle_post_trade(
        session,
        manager,
        result=result,
        strategy=strategy,
        strategy_id=strategy_id,
        wallet=wallet,
        symbol=symbol,
        market_price=market_price,
        action="BUY",
        reason=_decision_reason(live_decision),
        decision_source="rule_entry",
        is_sell=False,
    )
    _log_stage(
        session,
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage="final_execution",
        status="passed",
        reason_text="Trade executed after final sanity check",
        metrics_json=execution_readiness.metrics,
        context_json={"fatal_flags": execution_readiness.fatal_flags, "trade_id": result.trade.id},
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
        "reason": _decision_reason(live_decision),
        "decision_source": "rule_entry",
        "signal": _serialize_signal_result({
            "action": "BUY",
            "symbol": signal.symbol,
            "quantity_pct": quantity_pct,
            "reason": _decision_reason(live_decision),
        }),
    }


async def take_equity_snapshot(strategy_id: str, symbol: str | None = None) -> None:
    """Save current equity (cash + position value) as a snapshot."""
    async with SessionLocal() as session:
        result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        strategy = result.scalar_one_or_none()
        if strategy is None:
            return

        wallet = await get_or_create_wallet(session, strategy_id)
        positions = await get_positions(session, strategy_id)
        execution_mode = resolve_execution_mode(strategy)
        if execution_mode == MULTI_COIN_MODE:
            total = compute_total_equity(wallet, positions)
        else:
            resolved_symbol = str(symbol or resolve_primary_symbol(strategy)).upper()
            position = next((item for item in positions if item.symbol == resolved_symbol), None)
            total = wallet.available_usdt
            if position is not None:
                price = DataStore.get_instance().get_latest_price(resolved_symbol)
                if price is not None:
                    total += position.quantity * Decimal(str(price))

        snapshot = Snapshot(
            strategy_id=strategy_id,
            total_equity_usdt=total,
        )
        session.add(snapshot)
        await commit_with_write_lock(session)


async def strategy_loop(strategy_id: str, interval_seconds: int = 3600) -> None:
    """Continuous trading loop for a single strategy."""
    # Ensure loop never runs faster than the smallest candle interval (1m = 60s)
    interval_seconds = max(interval_seconds, 60)
    cycle = 0

    while True:
        try:
            result = await run_single_cycle(strategy_id)
            cycle += 1

            executed_count = 1 if result.get("status") == "executed" else int(
                (result.get("summary") or {}).get("executed", 0)
            )
            if executed_count > 0:
                logger.info(
                    "cycle complete strategy_id=%s cycle=%d executed=%d status=%s",
                    strategy_id,
                    cycle,
                    executed_count,
                    result.get("status"),
                )
                # Snapshot after every trade
                await take_equity_snapshot(strategy_id)
            elif result.get("status") in {"skipped", "hold"}:
                logger.debug(
                    "cycle complete strategy_id=%s cycle=%d status=%s reason=%s",
                    strategy_id, cycle, result.get("status"), result.get("reason"),
                )

            # Snapshot every cycle
            await take_equity_snapshot(strategy_id)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("strategy loop crashed strategy_id=%s", strategy_id)

        await asyncio.sleep(interval_seconds)
