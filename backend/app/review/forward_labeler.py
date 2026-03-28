"""
Forward labeler: computes fwd_ret_1/4/12/24 and max favorable/adverse excursion
for every ReviewLedger row that doesn't yet have forward outcome data.

Uses PriceCache (already populated by the engine). No external API calls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_cache import PriceCache
from app.models.review_ledger import ReviewForwardOutcome, ReviewLedger

logger = logging.getLogger(__name__)

# How many future candles to look ahead
_FORWARD_WINDOWS = (1, 4, 12, 24)
_MAX_WINDOW = max(_FORWARD_WINDOWS)


async def label_forward_outcomes(
    session: AsyncSession,
    strategy_id: str | None = None,
    cycle_id: str | None = None,
    limit: int = 500,
) -> int:
    """
    Compute and upsert forward outcomes for ledger rows that are missing them.

    Args:
        strategy_id: Restrict to a specific strategy (optional).
        cycle_id: Restrict to a specific cycle (optional).
        limit: Max rows to process in one call.

    Returns:
        Number of rows updated.
    """
    # Load ledger rows that need forward outcomes
    query = (
        select(ReviewLedger)
        .outerjoin(ReviewForwardOutcome, ReviewForwardOutcome.ledger_id == ReviewLedger.id)
        .where(ReviewForwardOutcome.id.is_(None))
        .where(ReviewLedger.cycle_ts.is_not(None))
    )
    if strategy_id:
        query = query.where(ReviewLedger.strategy_id == strategy_id)
    if cycle_id:
        query = query.where(ReviewLedger.cycle_id == cycle_id)
    query = query.limit(limit)

    result = await session.execute(query)
    pending: list[ReviewLedger] = list(result.scalars().all())

    if not pending:
        return 0

    updated = 0
    for entry in pending:
        outcome = await _compute_outcome(session, entry)
        session.add(outcome)
        updated += 1

    logger.info("forward_labeler: computed %d forward outcomes", updated)
    return updated


async def _compute_outcome(
    session: AsyncSession,
    entry: ReviewLedger,
) -> ReviewForwardOutcome:
    """Compute forward outcome for a single ledger entry."""
    decision_ts = entry.cycle_ts
    decision_price = entry.entry_price or None

    # Determine interval
    interval = entry.interval or "1h"

    # Use PriceCache to find candles after decision_ts
    decision_ts_ms = int(decision_ts.timestamp() * 1000) if decision_ts else 0

    result = await session.execute(
        select(PriceCache)
        .where(
            PriceCache.symbol == entry.symbol,
            PriceCache.interval == interval,
            PriceCache.open_time > decision_ts_ms,
        )
        .order_by(PriceCache.open_time)
        .limit(_MAX_WINDOW)
    )
    candles: list[PriceCache] = list(result.scalars().all())

    outcome = ReviewForwardOutcome(
        id=str(uuid4()),
        ledger_id=entry.id,
        symbol=entry.symbol,
        decision_ts=decision_ts,
        decision_price=decision_price,
        interval=interval,
        computed_at=datetime.now(timezone.utc),
    )

    if not candles or decision_price is None or decision_price == 0:
        outcome.fwd_data_available = False
        return outcome

    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]

    def ret(n: int) -> float | None:
        if len(closes) >= n:
            return (closes[n - 1] - decision_price) / decision_price * 100
        return None

    outcome.fwd_ret_1 = ret(1)
    outcome.fwd_ret_4 = ret(4)
    outcome.fwd_ret_12 = ret(12)
    outcome.fwd_ret_24 = ret(24)

    outcome.fwd_max_favorable_pct = (
        (max(highs) - decision_price) / decision_price * 100 if highs else None
    )
    outcome.fwd_max_adverse_pct = (
        (min(lows) - decision_price) / decision_price * 100 if lows else None
    )
    outcome.fwd_data_available = len(candles) >= _MAX_WINDOW

    return outcome
