"""
Report generator: produces Markdown reports + .meta.json sidecars.

Layer 1 (deterministic): queries ReviewLedger + ReviewForwardOutcome and
builds structured fact packets — tables, counts, root cause breakdowns.

Layer 2 (AI narrative): sends the fact packet to Claude and fills the
narrative sections. Falls back to a stub if AI is unavailable.

Output paths:
  backend/reports/daily/YYYY-MM-DD.md   + .meta.json
  backend/reports/weekly/YYYY-WXX.md    + .meta.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models.review_ledger import ReviewForwardOutcome, ReviewLedger
from app.review.outcome_classifier import (
    BUCKET_BAD_TRADE,
    BUCKET_GOOD_SKIP,
    BUCKET_GOOD_TRADE,
    BUCKET_MISSED_GOOD_TRADE,
    CAUSE_ALGORITHM,
    CAUSE_EXECUTION,
    CAUSE_MISMATCH,
    CAUSE_RANDOMNESS,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = BASE_DIR / "reports"


# ── Fact packet dataclasses ───────────────────────────────────────────

@dataclass
class TradeSummary:
    symbol: str
    entry_price: float | None
    exit_price: float | None
    pnl_pct: float | None
    hold_hours: float | None
    decision_source: str | None
    outcome_bucket: str | None
    root_cause: str | None
    root_cause_confidence: str | None
    composite_score: float | None
    regime: str | None
    setup_type: str | None


@dataclass
class MissedTrade:
    symbol: str
    rejection_stage: str | None
    rejection_reason_code: str | None
    no_execute_reason: str | None
    fwd_ret_24: float | None
    fwd_max_favorable_pct: float | None
    root_cause: str | None
    root_cause_confidence: str | None


@dataclass
class RootCauseCounts:
    algorithm_failure: int = 0
    execution_failure: int = 0
    strategy_mismatch: int = 0
    market_randomness: int = 0
    none: int = 0


@dataclass
class FactPacket:
    report_type: str
    period_start: str
    period_end: str
    strategies: list[str]
    cycles_covered: int
    trades_opened: int
    trades_closed: int
    open_positions: int
    missed_good_trades: int
    bad_trades: int
    good_skips: int
    good_trades: int
    root_cause_counts: RootCauseCounts
    trades: list[TradeSummary]
    missed: list[MissedTrade]
    confidence_score: float  # fraction of rows with fwd_data_available


# ── Fact builder ──────────────────────────────────────────────────────

async def _build_fact_packet(
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
    report_type: str,
) -> FactPacket:
    result = await session.execute(
        select(ReviewLedger)
        .outerjoin(ReviewForwardOutcome, ReviewForwardOutcome.ledger_id == ReviewLedger.id)
        .where(
            ReviewLedger.cycle_ts >= period_start,
            ReviewLedger.cycle_ts <= period_end,
        )
        .add_columns(ReviewForwardOutcome)
    )
    rows = result.all()

    strategies: set[str] = set()
    cycle_ids: set[str] = set()
    trades: list[TradeSummary] = []
    missed: list[MissedTrade] = []
    root_counts = RootCauseCounts()
    fwd_available_count = 0
    total_with_outcome = 0

    for entry, outcome in rows:
        strategies.add(entry.strategy_id)
        cycle_ids.add(entry.cycle_id)

        if outcome and outcome.fwd_data_available:
            fwd_available_count += 1
        if entry.outcome_bucket:
            total_with_outcome += 1

        bucket = entry.outcome_bucket
        cause = entry.root_cause

        if cause == CAUSE_ALGORITHM:
            root_counts.algorithm_failure += 1
        elif cause == CAUSE_EXECUTION:
            root_counts.execution_failure += 1
        elif cause == CAUSE_MISMATCH:
            root_counts.strategy_mismatch += 1
        elif cause == CAUSE_RANDOMNESS:
            root_counts.market_randomness += 1
        elif cause == "none" or cause is None:
            root_counts.none += 1

        if bucket in (BUCKET_GOOD_TRADE, BUCKET_BAD_TRADE) and entry.trade_opened:
            trades.append(TradeSummary(
                symbol=entry.symbol,
                entry_price=entry.entry_price,
                exit_price=entry.exit_price,
                pnl_pct=entry.realized_pnl_pct,
                hold_hours=entry.hold_duration_hours,
                decision_source=entry.decision_source,
                outcome_bucket=bucket,
                root_cause=cause,
                root_cause_confidence=entry.root_cause_confidence,
                composite_score=entry.composite_score,
                regime=entry.regime_at_decision,
                setup_type=entry.setup_type,
            ))

        if bucket == BUCKET_MISSED_GOOD_TRADE:
            missed.append(MissedTrade(
                symbol=entry.symbol,
                rejection_stage=entry.rejection_stage,
                rejection_reason_code=entry.rejection_reason_code,
                no_execute_reason=entry.no_execute_reason,
                fwd_ret_24=outcome.fwd_ret_24 if outcome else None,
                fwd_max_favorable_pct=outcome.fwd_max_favorable_pct if outcome else None,
                root_cause=cause,
                root_cause_confidence=entry.root_cause_confidence,
            ))

    counts: dict[str, int] = {}
    for entry, _ in rows:
        b = entry.outcome_bucket or "unknown"
        counts[b] = counts.get(b, 0) + 1

    confidence_score = (
        round(fwd_available_count / total_with_outcome, 2)
        if total_with_outcome > 0 else 0.0
    )

    return FactPacket(
        report_type=report_type,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        strategies=list(strategies),
        cycles_covered=len(cycle_ids),
        trades_opened=sum(1 for e, _ in rows if e.trade_opened),
        trades_closed=sum(1 for e, _ in rows if e.trade_closed),
        open_positions=sum(1 for e, _ in rows if e.position_still_open),
        missed_good_trades=counts.get(BUCKET_MISSED_GOOD_TRADE, 0),
        bad_trades=counts.get(BUCKET_BAD_TRADE, 0),
        good_skips=counts.get(BUCKET_GOOD_SKIP, 0),
        good_trades=counts.get(BUCKET_GOOD_TRADE, 0),
        root_cause_counts=root_counts,
        trades=trades,
        missed=missed,
        confidence_score=confidence_score,
    )


# ── Markdown builders ─────────────────────────────────────────────────

def _trade_table(trades: list[TradeSummary]) -> str:
    if not trades:
        return "_No trades in this period._\n"
    header = "| Symbol | Entry | Exit | PnL% | Hold (h) | Source | Outcome | Root Cause |\n"
    sep    = "|--------|-------|------|------|----------|--------|---------|------------|\n"
    rows = []
    for t in trades:
        rows.append(
            f"| {t.symbol} "
            f"| {t.entry_price:.4f} " if t.entry_price else "| — "
            f"| {t.exit_price:.4f} " if t.exit_price else "| — "
            f"| {t.pnl_pct:+.2f}% " if t.pnl_pct is not None else "| — "
            f"| {t.hold_hours:.1f} " if t.hold_hours else "| — "
            f"| {t.decision_source or '—'} "
            f"| {t.outcome_bucket or '—'} "
            f"| {t.root_cause or '—'} |"
        )
    return header + sep + "\n".join(rows) + "\n"


def _missed_table(missed: list[MissedTrade]) -> str:
    if not missed:
        return "_No missed good trades in this period._\n"
    header = "| Symbol | Rejected At | Reason Code | No-Execute | fwd_24% | Root Cause |\n"
    sep    = "|--------|-------------|-------------|------------|---------|------------|\n"
    rows = []
    for m in missed:
        rows.append(
            f"| {m.symbol} "
            f"| {m.rejection_stage or '—'} "
            f"| {m.rejection_reason_code or '—'} "
            f"| {m.no_execute_reason or '—'} "
            f"| {m.fwd_ret_24:+.2f}% " if m.fwd_ret_24 is not None else "| — "
            f"| {m.root_cause or '—'} |"
        )
    return header + sep + "\n".join(rows) + "\n"


def _root_cause_section(rc: RootCauseCounts) -> str:
    total = rc.algorithm_failure + rc.execution_failure + rc.strategy_mismatch + rc.market_randomness
    if total == 0:
        return "_No bad trades or missed opportunities classified._\n"

    def pct(n: int) -> str:
        return f"{n} ({n/total*100:.0f}%)" if total else str(n)

    return (
        f"| Root Cause | Count |\n"
        f"|------------|-------|\n"
        f"| Algorithm failure | {pct(rc.algorithm_failure)} |\n"
        f"| Execution failure | {pct(rc.execution_failure)} |\n"
        f"| Strategy mismatch | {pct(rc.strategy_mismatch)} |\n"
        f"| Market randomness | {pct(rc.market_randomness)} |\n"
    )


async def _ai_narrative(packet: FactPacket, report_type: str) -> dict[str, str]:
    """
    Call Claude to fill narrative sections. Returns a dict of section_name -> text.
    Falls back to stubs if AI is unavailable.
    """
    try:
        from app.config import get_settings
        settings = get_settings()
        if not settings.ai_enabled:
            raise RuntimeError("AI disabled")

        import anthropic  # type: ignore
        client = anthropic.AsyncAnthropic()

        packet_json = json.dumps(asdict(packet), indent=2, default=str)

        if report_type == "daily_operational":
            prompt = f"""You are a systematic trading auditor reviewing a paper trading system.

Here is the structured fact packet for today's trading session:

{packet_json}

Write the following sections for the daily operational report. Be concise and factual.
Cite specific symbols and ledger evidence. Mark uncertainty as "(evidence weak: N={{count}})".
Do NOT invent metrics not in the packet.

Return a JSON object with these keys:
- executive_summary: 2-3 sentences covering net result, notable events, top concern
- what_system_did: bullet points describing cycles, scans, selections
- trade_analysis: narrative analysis of each trade opened/closed
- action_items: ranked list of specific actionable items with expected impact
- good_skips: notable correct rejections worth preserving
"""
        else:
            prompt = f"""You are a systematic trading auditor reviewing a paper trading system's weekly performance.

Here is the structured fact packet for this week:

{packet_json}

Write the following sections for the weekly strategy review. Be analytical and pattern-focused.
Cite specific symbols, setup families, and regimes. Mark uncertainty where evidence is weak (N<3).
Do NOT invent metrics not in the packet.

Return a JSON object with these keys:
- executive_summary: 3-4 sentences covering weekly performance, dominant patterns, top insight
- strategy_scorecards: analysis of which setup families and regimes performed well vs poorly
- pattern_analysis: what keeps repeating — both good patterns to preserve and bad patterns to fix
- what_not_to_change: setups/rules generating consistent good_skips or good_trades
- action_items: ranked list with expected trades/week impact for each
"""

        response = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        # Claude should return JSON; parse it
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])

    except Exception as exc:
        logger.warning("review.report_generator: AI narrative skipped: %s", exc)
        return {}


def _render_daily(packet: FactPacket, narrative: dict[str, str]) -> str:
    rc = packet.root_cause_counts
    return f"""## Executive Summary

{narrative.get("executive_summary", "_AI narrative unavailable._")}

## What the System Did

- Cycles run: {packet.cycles_covered}
- Trades opened: {packet.trades_opened} | closed: {packet.trades_closed} | still open: {packet.open_positions}
- Missed good trades: {packet.missed_good_trades}
- Bad trades: {packet.bad_trades}
- Good skips: {packet.good_skips}

{narrative.get("what_system_did", "")}

## Trades Opened / Closed

{_trade_table(packet.trades)}

## Missed Good Trades

{_missed_table(packet.missed)}

## Root Cause Breakdown

{_root_cause_section(rc)}

## Good Skips Worth Noting

{narrative.get("good_skips", "_See appendix._")}

## Action Items

{narrative.get("action_items", "_No action items generated._")}

## Trade Analysis

{narrative.get("trade_analysis", "_No narrative generated._")}
"""


def _render_weekly(packet: FactPacket, narrative: dict[str, str]) -> str:
    rc = packet.root_cause_counts
    return f"""## Executive Summary

{narrative.get("executive_summary", "_AI narrative unavailable._")}

## Weekly Stats

- Cycles covered: {packet.cycles_covered}
- Trades opened: {packet.trades_opened} | closed: {packet.trades_closed}
- Good trades: {packet.good_trades} | Bad trades: {packet.bad_trades}
- Missed good trades: {packet.missed_good_trades} | Good skips: {packet.good_skips}
- Report confidence: {packet.confidence_score:.0%} (fraction of rows with forward data)

## Root Cause Breakdown

{_root_cause_section(rc)}

## Strategy Scorecards

{narrative.get("strategy_scorecards", "_Insufficient data for scorecards._")}

## Pattern Analysis

{narrative.get("pattern_analysis", "_No patterns identified._")}

## What NOT to Change

{narrative.get("what_not_to_change", "_No stable patterns identified yet._")}

## Action Items (Ranked by Expected Impact)

{narrative.get("action_items", "_No action items generated._")}

## Missed Good Trades

{_missed_table(packet.missed)}

## Bad Trades

{_trade_table([t for t in packet.trades if t.outcome_bucket == "bad_trade"])}
"""


def _frontmatter(packet: FactPacket, iso_label: str) -> str:
    rc = packet.root_cause_counts
    return (
        f"---\n"
        f"report_type: {packet.report_type}\n"
        f"period_start: {packet.period_start}\n"
        f"period_end: {packet.period_end}\n"
        f"generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"label: {iso_label}\n"
        f"cycles_covered: {packet.cycles_covered}\n"
        f"trades_opened: {packet.trades_opened}\n"
        f"trades_closed: {packet.trades_closed}\n"
        f"open_positions: {packet.open_positions}\n"
        f"missed_good_trades: {packet.missed_good_trades}\n"
        f"bad_trades: {packet.bad_trades}\n"
        f"good_skips: {packet.good_skips}\n"
        f"good_trades: {packet.good_trades}\n"
        f"confidence_score: {packet.confidence_score}\n"
        f"root_cause_counts:\n"
        f"  algorithm_failure: {rc.algorithm_failure}\n"
        f"  execution_failure: {rc.execution_failure}\n"
        f"  strategy_mismatch: {rc.strategy_mismatch}\n"
        f"  market_randomness: {rc.market_randomness}\n"
        f"---\n\n"
    )


def _write_report(directory: Path, label: str, content: str, meta: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    md_path = directory / f"{label}.md"
    meta_path = directory / f"{label}.meta.json"
    md_path.write_text(content, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return md_path


# ── Public API ────────────────────────────────────────────────────────

async def generate_daily_report(date: date | None = None) -> Path:
    """Generate the daily operational report for a given date (default: yesterday)."""
    if date is None:
        date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    period_start = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=timezone.utc)
    period_end   = datetime(date.year, date.month, date.day, 23, 59, 59, tzinfo=timezone.utc)
    label = date.isoformat()

    async with SessionLocal() as session:
        packet = await _build_fact_packet(session, period_start, period_end, "daily_operational")

    narrative = await _ai_narrative(packet, "daily_operational")
    fm = _frontmatter(packet, label)
    body = _render_daily(packet, narrative)
    content = fm + body

    meta = {
        **asdict(packet),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_path": f"reports/daily/{label}.md",
        "label": label,
    }

    return _write_report(REPORTS_DIR / "daily", label, content, meta)


async def generate_weekly_report(ref_date: date | None = None) -> Path:
    """Generate the weekly strategy review. ref_date defaults to today; covers the prior Mon–Sun."""
    if ref_date is None:
        ref_date = datetime.now(timezone.utc).date()

    # Find the most recent completed Mon–Sun week
    monday = ref_date - timedelta(days=ref_date.weekday() + 7)
    sunday = monday + timedelta(days=6)
    iso_week = monday.strftime("%G-W%V")

    period_start = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=timezone.utc)
    period_end   = datetime(sunday.year, sunday.month, sunday.day, 23, 59, 59, tzinfo=timezone.utc)

    async with SessionLocal() as session:
        packet = await _build_fact_packet(session, period_start, period_end, "weekly_strategy_review")

    narrative = await _ai_narrative(packet, "weekly_strategy_review")
    fm = _frontmatter(packet, iso_week)
    body = _render_weekly(packet, narrative)
    content = fm + body

    meta = {
        **asdict(packet),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_path": f"reports/weekly/{iso_week}.md",
        "label": iso_week,
    }

    return _write_report(REPORTS_DIR / "weekly", iso_week, content, meta)
