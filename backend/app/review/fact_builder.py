"""
Fact builder: materializes one ReviewLedger row per (strategy_id, cycle_id, symbol)
by joining SymbolEvaluationLog, DailyPick, Trade, and AICallLog.

Called after each cycle completes. Deterministic — no AI involvement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_call_log import AICallLog
from app.models.daily_pick import DailyPick
from app.models.enums import TradeSide
from app.models.review_ledger import ReviewLedger
from app.models.strategy import Strategy
from app.models.symbol_evaluation_log import SymbolEvaluationLog
from app.models.trade import Trade

logger = logging.getLogger(__name__)

# Stage names written by the engine and scanner
_STAGE_UNIVERSE = "universe"
_STAGE_TRADABILITY = "tradability"
_STAGE_DATA_CHECK = "data_check"
_STAGE_SETUP_DETECTION = "setup_detection"
_STAGE_LIQUIDITY_FLOOR = "liquidity_floor"

# Candle-interval in hours for hold duration computation
_INTERVAL_HOURS: dict[str, float] = {
    "1m": 1 / 60,
    "5m": 5 / 60,
    "15m": 15 / 60,
    "1h": 1.0,
    "4h": 4.0,
    "1d": 24.0,
}

# Reason codes that indicate execution was blocked (not a strategy decision)
_EXECUTION_BLOCK_CODES = {
    "AI_HOLD",
    "AI_ERROR",
    "AI_COOLDOWN",
    "WALLET_INSUFFICIENT",
    "MAX_POSITIONS_REACHED",
    "MAX_EXPOSURE_REACHED",
    "SYMBOL_OWNERSHIP_CONFLICT",
    "COOLDOWN_ACTIVE",
    "DAILY_LOSS_LIMIT",
    "LOCK_CONTENTION",
}


def _stage_status(logs: list[SymbolEvaluationLog], stage: str) -> str | None:
    """Return the status for a specific stage, or None if the stage wasn't logged."""
    for log in logs:
        if log.stage.lower() == stage.lower():
            return log.status
    return None


def _first_failure(logs: list[SymbolEvaluationLog]) -> SymbolEvaluationLog | None:
    """Return the first log entry with a failure/rejection status."""
    failure_statuses = {"fail", "failed", "reject", "rejected", "skipped"}
    for log in sorted(logs, key=lambda x: x.created_at):
        if log.status.lower() in failure_statuses:
            return log
    return None


def _passes(logs: list[SymbolEvaluationLog], stage: str) -> bool | None:
    status = _stage_status(logs, stage)
    if status is None:
        return None
    return status.lower() in {"pass", "passed", "ok", "success"}


async def build_cycle_ledger(
    session: AsyncSession,
    strategy_id: str,
    cycle_id: str,
    cycle_ts: datetime | None = None,
    interval: str | None = None,
) -> list[ReviewLedger]:
    """
    Build ReviewLedger rows for every symbol touched in this cycle.
    Upserts by (strategy_id, cycle_id, symbol) — safe to call multiple times.
    Returns the list of upserted entries.
    """
    # ── 1. Load all eval logs for this cycle ──────────────────────────
    result = await session.execute(
        select(SymbolEvaluationLog)
        .where(
            SymbolEvaluationLog.strategy_id == strategy_id,
            SymbolEvaluationLog.cycle_id == cycle_id,
        )
        .order_by(SymbolEvaluationLog.created_at)
    )
    all_eval_logs: list[SymbolEvaluationLog] = list(result.scalars().all())

    if not all_eval_logs:
        logger.debug("fact_builder: no eval logs for cycle_id=%s, skipping", cycle_id)
        return []

    # Group by symbol
    logs_by_symbol: dict[str, list[SymbolEvaluationLog]] = {}
    for log in all_eval_logs:
        logs_by_symbol.setdefault(log.symbol, []).append(log)

    cycle_ts = cycle_ts or min(log.created_at for log in all_eval_logs)
    selection_date = cycle_ts.date() if hasattr(cycle_ts, "date") else datetime.now(timezone.utc).date()

    # ── 2. Load daily picks for the same strategy + date ─────────────
    result = await session.execute(
        select(DailyPick).where(
            DailyPick.strategy_id == strategy_id,
            DailyPick.selection_date == selection_date,
        )
    )
    daily_picks = result.scalars().all()
    picks_by_symbol: dict[str, DailyPick] = {p.symbol: p for p in daily_picks}

    # ── 3. Load all BUY trades within a 2h window of cycle_ts ────────
    from datetime import timedelta
    window_start = cycle_ts - timedelta(hours=1)
    window_end = cycle_ts + timedelta(hours=2)

    result = await session.execute(
        select(Trade).where(
            Trade.strategy_id == strategy_id,
            Trade.side == TradeSide.BUY,
            Trade.executed_at >= window_start,
            Trade.executed_at <= window_end,
        )
    )
    buy_trades: list[Trade] = list(result.scalars().all())
    buy_by_symbol: dict[str, Trade] = {t.symbol: t for t in buy_trades}

    # ── 4. Load SELL trades for symbols that were bought ─────────────
    bought_symbols = set(buy_by_symbol.keys())
    sell_by_symbol: dict[str, Trade] = {}
    if bought_symbols:
        result = await session.execute(
            select(Trade).where(
                Trade.strategy_id == strategy_id,
                Trade.side == TradeSide.SELL,
                Trade.symbol.in_(bought_symbols),
                Trade.executed_at >= window_start,
            )
        )
        for t in result.scalars().all():
            # Keep the first SELL after the BUY
            buy = buy_by_symbol.get(t.symbol)
            if buy and t.executed_at > buy.executed_at:
                existing = sell_by_symbol.get(t.symbol)
                if existing is None or t.executed_at < existing.executed_at:
                    sell_by_symbol[t.symbol] = t

    # ── 5. Load AI call logs within cycle window ──────────────────────
    result = await session.execute(
        select(AICallLog).where(
            AICallLog.strategy_id == strategy_id,
            AICallLog.created_at >= window_start,
            AICallLog.created_at <= window_end,
        )
    )
    ai_by_symbol: dict[str, AICallLog] = {}
    for ai in result.scalars().all():
        ai_by_symbol.setdefault(ai.symbol, ai)

    # ── 6. Compute universe_size and per-symbol ranks ─────────────────
    universe_symbols = {
        sym for sym, logs in logs_by_symbol.items()
        if _stage_status(logs, _STAGE_UNIVERSE) is not None
    }
    universe_size = len(universe_symbols)

    qualified_with_score: list[tuple[str, float]] = []
    for sym, logs in logs_by_symbol.items():
        if _all_gates_pass(logs):
            score = picks_by_symbol[sym].scanner_net_quality_score if sym in picks_by_symbol else 0.0
            qualified_with_score.append((sym, score or 0.0))
    qualified_with_score.sort(key=lambda x: x[1], reverse=True)
    rank_map = {sym: i + 1 for i, (sym, _) in enumerate(qualified_with_score)}

    # ── 7. Resolve strategy interval ─────────────────────────────────
    if not interval:
        result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        strategy = result.scalar_one_or_none()
        if strategy:
            config = strategy.config_json or {}
            interval = strategy.candle_interval or config.get("candle_interval", "1h")
        else:
            interval = "1h"

    interval_hours = _INTERVAL_HOURS.get(interval, 1.0)

    # ── 8. Build ledger rows ──────────────────────────────────────────
    built: list[ReviewLedger] = []

    for symbol, logs in logs_by_symbol.items():
        # Check for existing row to upsert
        result = await session.execute(
            select(ReviewLedger).where(
                ReviewLedger.strategy_id == strategy_id,
                ReviewLedger.cycle_id == cycle_id,
                ReviewLedger.symbol == symbol,
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            entry = ReviewLedger(
                id=str(uuid4()),
                strategy_id=strategy_id,
                cycle_id=cycle_id,
            )
            session.add(entry)

        # Identity
        entry.cycle_ts = cycle_ts
        entry.symbol = symbol
        entry.interval = interval

        # Gating
        entry.in_universe = _stage_status(logs, _STAGE_UNIVERSE) is not None
        entry.tradability_pass = _passes(logs, _STAGE_TRADABILITY)
        entry.data_sufficient = _passes(logs, _STAGE_DATA_CHECK)
        entry.setup_detected = _passes(logs, _STAGE_SETUP_DETECTION)
        entry.liquidity_pass = _passes(logs, _STAGE_LIQUIDITY_FLOOR)
        entry.final_gate_pass = _all_gates_pass(logs)

        first_fail = _first_failure(logs)
        if first_fail:
            entry.rejection_stage = first_fail.stage
            entry.rejection_reason_code = first_fail.reason_code
            entry.rejection_reason_text = first_fail.reason_text

        # Setup from eval logs or daily pick
        pick = picks_by_symbol.get(symbol)
        if pick:
            entry.setup_type = pick.setup_type
            entry.setup_family = pick.scanner_family
            entry.daily_pick_rank = pick.rank
            entry.scanner_score = pick.scanner_net_quality_score
            entry.regime_at_decision = pick.regime or pick.scanner_detailed_regime
            entry.regime_fit_score = pick.regime_fit_score
            entry.setup_fit_score = pick.setup_fit_score
        else:
            # Try to extract from metrics_json of setup detection log
            for log in logs:
                if log.stage.lower() == _STAGE_SETUP_DETECTION and log.metrics_json:
                    entry.setup_type = log.metrics_json.get("setup_type") or entry.setup_type
                    entry.setup_family = log.metrics_json.get("family") or entry.setup_family
                    entry.regime_at_decision = (
                        log.context_json.get("regime") if log.context_json else None
                    ) or entry.regime_at_decision

        entry.universe_size = universe_size
        entry.rank_among_qualified = rank_map.get(symbol)

        # AI
        ai = ai_by_symbol.get(symbol)
        if ai:
            entry.ai_called = True
            entry.ai_action = ai.action
            entry.ai_confidence = float(ai.confidence) if ai.confidence else None
            entry.ai_status = ai.status
            entry.ai_cost_usdt = float(ai.cost_usdt) if ai.cost_usdt else None
            entry.ai_reasoning_snippet = (ai.reasoning or "")[:500] or None
        else:
            entry.ai_called = False

        # Execution
        buy = buy_by_symbol.get(symbol)
        if buy:
            entry.trade_opened = True
            entry.entry_price = float(buy.price)
            entry.market_price_at_entry = float(buy.market_price)
            if buy.market_price and buy.market_price != 0:
                entry.slippage_pct = float(
                    (buy.price - buy.market_price) / buy.market_price * 100
                )
            entry.entry_fee_usdt = float(buy.fee) if buy.fee else None
            entry.position_size_usdt = float(buy.cost_usdt) if buy.cost_usdt else None
            entry.wallet_balance_before_usdt = (
                float(buy.wallet_balance_before) if buy.wallet_balance_before else None
            )
            if entry.position_size_usdt and entry.wallet_balance_before_usdt:
                entry.exposure_pct = entry.position_size_usdt / entry.wallet_balance_before_usdt * 100
            entry.composite_score = float(buy.composite_score) if buy.composite_score else None
            entry.entry_confidence = float(buy.entry_confidence_final) if buy.entry_confidence_final else None
            entry.confidence_bucket = buy.entry_confidence_bucket
            entry.indicator_snapshot = buy.indicator_snapshot
            entry.decision_source = buy.decision_source
        else:
            entry.trade_opened = False
            # Classify why a qualified symbol wasn't traded
            if entry.final_gate_pass:
                entry.no_execute_reason = _infer_no_execute_reason(ai, logs)

        # Position lifecycle
        sell = sell_by_symbol.get(symbol)
        if sell and buy:
            entry.trade_closed = True
            entry.exit_price = float(sell.price)
            entry.exit_fee_usdt = float(sell.fee) if sell.fee else None
            entry.realized_pnl_usdt = float(sell.pnl) if sell.pnl else None
            entry.realized_pnl_pct = float(sell.pnl_pct) if sell.pnl_pct else None
            entry.exit_reason = sell.decision_source
            entry.position_still_open = False
            if buy.executed_at and sell.executed_at:
                delta_hours = (
                    sell.executed_at - buy.executed_at
                ).total_seconds() / 3600
                entry.hold_duration_hours = delta_hours
                entry.hold_duration_candles = delta_hours / interval_hours if interval_hours else None
        elif buy and not sell:
            entry.position_still_open = True
            entry.trade_closed = False
        else:
            entry.position_still_open = False
            entry.trade_closed = False

        entry.updated_at = datetime.now(timezone.utc)
        built.append(entry)

    logger.info(
        "fact_builder: upserted %d ledger rows strategy_id=%s cycle_id=%s",
        len(built),
        strategy_id,
        cycle_id,
    )
    return built


def _all_gates_pass(logs: list[SymbolEvaluationLog]) -> bool:
    """Return True if the symbol passed all required gates in this cycle."""
    # Must have been in universe and have no failure logs
    has_universe = any(log.stage.lower() == _STAGE_UNIVERSE for log in logs)
    if not has_universe:
        return False
    failure_statuses = {"fail", "failed", "reject", "rejected"}
    for log in logs:
        if log.status.lower() in failure_statuses:
            return False
    return True


def _infer_no_execute_reason(
    ai: AICallLog | None,
    logs: list[SymbolEvaluationLog],
) -> str:
    """Infer why a gate-passing symbol wasn't traded."""
    if ai:
        if ai.status == "error":
            return "AI_ERROR"
        if ai.action and ai.action.lower() in {"hold", "skip"}:
            return "AI_HOLD"
        if ai.skip_reason == "cooldown":
            return "AI_COOLDOWN"

    # Check eval logs for execution-stage failures
    exec_reason_map = {
        "wallet_insufficient": "WALLET_INSUFFICIENT",
        "max_positions": "MAX_POSITIONS_REACHED",
        "max_exposure": "MAX_EXPOSURE_REACHED",
        "symbol_ownership": "SYMBOL_OWNERSHIP_CONFLICT",
        "cooldown": "COOLDOWN_ACTIVE",
        "daily_loss_limit": "DAILY_LOSS_LIMIT",
        "lock_contention": "LOCK_CONTENTION",
    }
    for log in logs:
        if log.reason_code:
            key = log.reason_code.lower()
            for pattern, code in exec_reason_map.items():
                if pattern in key:
                    return code

    return "UNKNOWN"
