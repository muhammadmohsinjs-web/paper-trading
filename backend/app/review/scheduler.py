"""
Review background scheduler.

Runs two periodic jobs inside the existing asyncio event loop:
  - forward_labeler : every 4 h  — fills fwd_ret_* for ledger rows
  - outcome_classifier : every 4 h (after labeler) — assigns outcome_bucket + root_cause
  - daily_report : once per day at 01:00 UTC
  - weekly_report : once per week on Monday at 06:00 UTC

Start via start_review_scheduler() from main.py lifespan.
Stop via stop_review_scheduler() on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None

FORWARD_LABEL_INTERVAL_HOURS = 4
CLASSIFY_INTERVAL_HOURS = 4
DAILY_REPORT_HOUR_UTC = 1      # 01:00 UTC
WEEKLY_REPORT_HOUR_UTC = 6     # 06:00 UTC Monday


async def _run_forward_labeler() -> None:
    from app.database import SessionLocal, commit_with_write_lock
    from app.review.forward_labeler import label_forward_outcomes

    try:
        async with SessionLocal() as session:
            n = await label_forward_outcomes(session, limit=1000)
            await commit_with_write_lock(session)
        logger.info("review.scheduler: forward_labeler updated %d rows", n)
    except Exception:
        logger.exception("review.scheduler: forward_labeler failed")


async def _run_classifier() -> None:
    from app.database import SessionLocal, commit_with_write_lock
    from app.review.outcome_classifier import classify_pending

    try:
        async with SessionLocal() as session:
            n = await classify_pending(session, limit=1000)
            await commit_with_write_lock(session)
        logger.info("review.scheduler: classifier updated %d rows", n)
    except Exception:
        logger.exception("review.scheduler: classifier failed")


async def _run_daily_report() -> None:
    from app.review.report_generator import generate_daily_report

    try:
        today = datetime.now(timezone.utc).date()
        path = await generate_daily_report(date=today)
        logger.info("review.scheduler: daily report written to %s", path)
    except Exception:
        logger.exception("review.scheduler: daily report failed")


async def _run_weekly_report() -> None:
    from app.review.report_generator import generate_weekly_report

    try:
        path = await generate_weekly_report()
        logger.info("review.scheduler: weekly report written to %s", path)
    except Exception:
        logger.exception("review.scheduler: weekly report failed")


def _seconds_until(hour_utc: int) -> float:
    """Seconds until the next occurrence of hour_utc:00 UTC."""
    now = datetime.now(timezone.utc)
    next_run = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run = next_run.replace(day=next_run.day + 1)
    return (next_run - now).total_seconds()


async def _scheduler_loop() -> None:
    logger.info("review.scheduler: started")
    label_interval = FORWARD_LABEL_INTERVAL_HOURS * 3600
    last_label = 0.0
    last_daily_date: datetime.date | None = None
    last_weekly_iso: str | None = None

    # Run labeler + classifier immediately on startup to catch any backlog
    await _run_forward_labeler()
    await _run_classifier()

    while True:
        try:
            await asyncio.sleep(60)  # tick every minute
            now = datetime.now(timezone.utc)
            loop_time = asyncio.get_event_loop().time()

            # ── Forward labeler + classifier every 4 h ────────────────
            if loop_time - last_label >= label_interval:
                await _run_forward_labeler()
                await _run_classifier()
                last_label = loop_time

            # ── Daily report at 01:00 UTC ─────────────────────────────
            today = now.date()
            if (
                now.hour == DAILY_REPORT_HOUR_UTC
                and now.minute < 5
                and last_daily_date != today
            ):
                await _run_daily_report()
                last_daily_date = today

            # ── Weekly report Monday 06:00 UTC ────────────────────────
            iso_week = now.strftime("%G-W%V")
            if (
                now.weekday() == 0  # Monday
                and now.hour == WEEKLY_REPORT_HOUR_UTC
                and now.minute < 5
                and last_weekly_iso != iso_week
            ):
                await _run_weekly_report()
                last_weekly_iso = iso_week

        except asyncio.CancelledError:
            logger.info("review.scheduler: stopping")
            break
        except Exception:
            logger.exception("review.scheduler: unexpected error in tick, continuing")


def start_review_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="review-scheduler")


async def stop_review_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is None:
        return
    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass
    _scheduler_task = None
