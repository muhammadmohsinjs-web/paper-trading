"""
Outcome classifier: assigns outcome_bucket and root_cause to ReviewLedger rows
that have complete forward outcome data.

All rules are deterministic — no AI. Thresholds are config-driven via
CLASSIFIER_CONFIG, which can be overridden at runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_ledger import ReviewForwardOutcome, ReviewLedger

logger = logging.getLogger(__name__)

# Outcome bucket values
BUCKET_GOOD_TRADE = "good_trade"
BUCKET_BAD_TRADE = "bad_trade"
BUCKET_GOOD_SKIP = "good_skip"
BUCKET_MISSED_GOOD_TRADE = "missed_good_trade"
BUCKET_OPEN = "open"
BUCKET_INSUFFICIENT_DATA = "insufficient_data"

# Root cause values
CAUSE_ALGORITHM = "algorithm_failure"
CAUSE_EXECUTION = "execution_failure"
CAUSE_MISMATCH = "strategy_mismatch"
CAUSE_RANDOMNESS = "market_randomness"
CAUSE_NONE = "none"

# Confidence values
CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"

# Execution-blocking no_execute_reason codes (from fact_builder)
_EXECUTION_BLOCK_CODES = {
    "WALLET_INSUFFICIENT",
    "MAX_POSITIONS_REACHED",
    "MAX_EXPOSURE_REACHED",
    "SYMBOL_OWNERSHIP_CONFLICT",
    "COOLDOWN_ACTIVE",
    "DAILY_LOSS_LIMIT",
    "LOCK_CONTENTION",
    "AI_ERROR",
}

# Regimes that make breakout setups inherently risky
_UNFAVORABLE_REGIMES = {"bear", "high_volatility", "downtrend"}


@dataclass
class ClassifierConfig:
    # Minimum forward return to call a skip/miss a "missed good trade"
    missed_opportunity_threshold_pct: float = 3.0
    # Maximum realized loss to flag as "bad trade"
    bad_trade_loss_threshold_pct: float = -2.0
    # Minimum composite score for a "well-reasoned" entry
    good_entry_score_threshold: float = 0.55
    # Slippage above this is flagged as execution degradation
    high_slippage_threshold_pct: float = 0.5
    # Max adverse move within first 4 candles to classify as market randomness
    fast_adverse_move_threshold_pct: float = -3.0
    # Minimum hold to rule out premature stop
    min_healthy_hold_candles: float = 2.0
    # Minimum regime fit to be considered "good entry in correct regime"
    min_regime_fit_score: float = 0.6


CLASSIFIER_CONFIG = ClassifierConfig()


async def classify_pending(
    session: AsyncSession,
    strategy_id: str | None = None,
    cycle_id: str | None = None,
    limit: int = 500,
) -> int:
    """
    Classify ledger rows that have forward outcomes but no outcome_bucket yet.

    Returns number of rows classified.
    """
    query = (
        select(ReviewLedger, ReviewForwardOutcome)
        .join(ReviewForwardOutcome, ReviewForwardOutcome.ledger_id == ReviewLedger.id)
        .where(ReviewLedger.outcome_bucket.is_(None))
        .where(ReviewLedger.position_still_open.is_(False))
    )
    if strategy_id:
        query = query.where(ReviewLedger.strategy_id == strategy_id)
    if cycle_id:
        query = query.where(ReviewLedger.cycle_id == cycle_id)
    query = query.limit(limit)

    result = await session.execute(query)
    rows = result.all()

    classified = 0
    for entry, outcome in rows:
        _classify_entry(entry, outcome, CLASSIFIER_CONFIG)
        classified += 1

    logger.info("outcome_classifier: classified %d rows", classified)
    return classified


def _classify_entry(
    entry: ReviewLedger,
    outcome: ReviewForwardOutcome,
    cfg: ClassifierConfig,
) -> None:
    """Apply bucket and root cause rules to a single ledger entry in-place."""
    cfg = cfg or CLASSIFIER_CONFIG

    # ── Insufficient data guard ───────────────────────────────────────
    if not outcome.fwd_data_available and not entry.trade_closed:
        entry.outcome_bucket = BUCKET_INSUFFICIENT_DATA
        entry.root_cause = CAUSE_NONE
        entry.root_cause_confidence = CONF_LOW
        return

    # ── Open positions ────────────────────────────────────────────────
    if entry.position_still_open:
        entry.outcome_bucket = BUCKET_OPEN
        entry.root_cause = CAUSE_NONE
        entry.root_cause_confidence = CONF_HIGH
        return

    fwd_24 = outcome.fwd_ret_24
    fwd_4 = outcome.fwd_ret_4
    fwd_max_adverse = outcome.fwd_max_adverse_pct

    # ── Not traded ────────────────────────────────────────────────────
    if not entry.trade_opened:
        missed = (
            fwd_24 is not None
            and fwd_24 > cfg.missed_opportunity_threshold_pct
        )
        entry.outcome_bucket = BUCKET_MISSED_GOOD_TRADE if missed else BUCKET_GOOD_SKIP
        entry.root_cause = CAUSE_NONE

        if missed:
            entry.root_cause, entry.root_cause_confidence = _root_cause_for_miss(entry, outcome, cfg)
        else:
            entry.root_cause_confidence = CONF_HIGH if outcome.fwd_data_available else CONF_LOW
        return

    # ── Traded and closed ─────────────────────────────────────────────
    pnl_pct = entry.realized_pnl_pct
    score = entry.composite_score or 0.0

    if pnl_pct is None:
        entry.outcome_bucket = BUCKET_INSUFFICIENT_DATA
        entry.root_cause = CAUSE_NONE
        entry.root_cause_confidence = CONF_LOW
        return

    is_good_entry = score >= cfg.good_entry_score_threshold
    is_bad_outcome = pnl_pct < cfg.bad_trade_loss_threshold_pct

    if not is_bad_outcome:
        entry.outcome_bucket = BUCKET_GOOD_TRADE
        entry.root_cause = CAUSE_NONE
        entry.root_cause_confidence = CONF_HIGH
        return

    # Bad outcome — always a bad trade; determine root cause
    entry.outcome_bucket = BUCKET_BAD_TRADE
    entry.root_cause, entry.root_cause_confidence = _root_cause_for_bad_trade(
        entry, outcome, cfg
    )


def _root_cause_for_miss(
    entry: ReviewLedger,
    outcome: ReviewForwardOutcome,
    cfg: ClassifierConfig,
) -> tuple[str, str]:
    """Classify root cause for a missed good trade."""
    causes: list[str] = []

    # Execution block (not a strategy call)
    if entry.no_execute_reason in _EXECUTION_BLOCK_CODES:
        causes.append(CAUSE_EXECUTION)

    # Algorithm filtered it incorrectly
    if entry.rejection_reason_code:
        code = entry.rejection_reason_code.upper()
        fwd_favorable = outcome.fwd_max_favorable_pct or 0.0
        if code == "LIQUIDITY_TOO_LOW" and fwd_favorable > 5.0:
            causes.append(CAUSE_ALGORITHM)
        if code == "MARKET_DATA_INSUFFICIENT" and outcome.fwd_data_available:
            causes.append(CAUSE_ALGORITHM)

    if len(causes) == 1:
        return causes[0], CONF_HIGH
    if len(causes) > 1:
        return causes[0], CONF_MEDIUM
    return CAUSE_NONE, CONF_LOW


def _root_cause_for_bad_trade(
    entry: ReviewLedger,
    outcome: ReviewForwardOutcome,
    cfg: ClassifierConfig,
) -> tuple[str, str]:
    """Classify root cause for a bad trade."""
    causes: list[str] = []

    score = entry.composite_score or 0.0
    regime = (entry.regime_at_decision or "").lower()
    hold = entry.hold_duration_candles or 0.0
    slippage = entry.slippage_pct or 0.0
    regime_fit = entry.regime_fit_score or 0.0
    fwd_4 = outcome.fwd_ret_4 or 0.0
    fwd_max_adverse = outcome.fwd_max_adverse_pct or 0.0
    setup_family = (entry.setup_family or "").lower()
    indicators = entry.indicator_snapshot or {}

    # ── Algorithm failure ─────────────────────────────────────────────
    # Contradicting indicators at entry (e.g. overbought RSI on breakout entry)
    rsi = indicators.get("rsi")
    if (
        rsi is not None
        and "breakout" in setup_family
        and float(rsi) > 70
    ):
        causes.append(CAUSE_ALGORITHM)

    # Bad entry in an unfavorable regime with no regime gate
    if regime in _UNFAVORABLE_REGIMES and score < cfg.good_entry_score_threshold:
        causes.append(CAUSE_ALGORITHM)

    # ── Execution failure ─────────────────────────────────────────────
    if slippage > cfg.high_slippage_threshold_pct:
        causes.append(CAUSE_EXECUTION)

    # ── Strategy mismatch ─────────────────────────────────────────────
    # Regime mismatch: unfavorable regime but decent score (strategy has no gate)
    if regime in _UNFAVORABLE_REGIMES and score >= cfg.good_entry_score_threshold:
        causes.append(CAUSE_MISMATCH)

    # Stop triggered before setup played out
    if hold < cfg.min_healthy_hold_candles:
        causes.append(CAUSE_MISMATCH)

    # Setup detected but no forward opportunity existed
    if (
        entry.setup_detected
        and outcome.fwd_max_favorable_pct is not None
        and outcome.fwd_max_favorable_pct < 0.5
    ):
        causes.append(CAUSE_MISMATCH)

    # ── Market randomness ─────────────────────────────────────────────
    # Good entry score, good regime fit, but fast sharp move against position
    fast_adverse = fwd_4 < cfg.fast_adverse_move_threshold_pct
    if (
        score >= cfg.good_entry_score_threshold
        and regime_fit >= cfg.min_regime_fit_score
        and fast_adverse
        and CAUSE_ALGORITHM not in causes
        and CAUSE_MISMATCH not in causes
    ):
        causes.append(CAUSE_RANDOMNESS)

    # ── Resolve ───────────────────────────────────────────────────────
    if not causes:
        # Fallback: good entry that just lost — market randomness
        if score >= cfg.good_entry_score_threshold:
            return CAUSE_RANDOMNESS, CONF_MEDIUM
        return CAUSE_ALGORITHM, CONF_LOW

    if len(causes) == 1:
        return causes[0], CONF_HIGH

    # Multiple causes: pick the one with highest priority
    priority = [CAUSE_ALGORITHM, CAUSE_EXECUTION, CAUSE_MISMATCH, CAUSE_RANDOMNESS]
    for cause in priority:
        if cause in causes:
            return cause, CONF_MEDIUM

    return causes[0], CONF_MEDIUM
