from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class ReviewLedger(UUIDPrimaryKeyMixin, Base):
    """One row per (strategy_id, cycle_id, symbol). Materialized after each cycle."""

    __tablename__ = "review_ledger"
    __table_args__ = (
        UniqueConstraint("strategy_id", "cycle_id", "symbol", name="uq_review_ledger_strategy_cycle_symbol"),
    )

    # ── Identity ──────────────────────────────────────────────────────
    strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cycle_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cycle_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    interval: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    # ── Universe & gating ─────────────────────────────────────────────
    in_universe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tradability_pass: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    data_sufficient: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    setup_detected: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    setup_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    setup_family: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    liquidity_pass: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    final_gate_pass: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rejection_reason_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rejection_reason_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Ranking context ───────────────────────────────────────────────
    daily_pick_rank: Mapped[Optional[int]] = mapped_column(nullable=True)
    scanner_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    regime_at_decision: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    regime_fit_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    setup_fit_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    universe_size: Mapped[Optional[int]] = mapped_column(nullable=True)
    rank_among_qualified: Mapped[Optional[int]] = mapped_column(nullable=True)

    # ── AI decision ───────────────────────────────────────────────────
    ai_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_action: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ai_cost_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_reasoning_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Execution ─────────────────────────────────────────────────────
    trade_opened: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_price_at_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_fee_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_size_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wallet_balance_before_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exposure_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    composite_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_bucket: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    indicator_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    decision_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    no_execute_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ── Position lifecycle ────────────────────────────────────────────
    trade_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_fee_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_pnl_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    hold_duration_candles: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hold_duration_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_still_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Outcome classification ────────────────────────────────────────
    # Values: good_trade, bad_trade, good_skip, missed_good_trade, open, insufficient_data
    outcome_bucket: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    # Values: algorithm_failure, execution_failure, strategy_mismatch, market_randomness, none
    root_cause: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    # Values: high, medium, low
    root_cause_confidence: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    strategy = relationship("Strategy", backref="review_ledger_entries")


class ReviewForwardOutcome(UUIDPrimaryKeyMixin, Base):
    """Forward price outcomes for every symbol considered in a cycle."""

    __tablename__ = "review_forward_outcomes"
    __table_args__ = (
        UniqueConstraint("ledger_id", name="uq_review_forward_outcomes_ledger"),
    )

    ledger_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_ledger.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    decision_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interval: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    fwd_ret_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fwd_ret_4: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fwd_ret_12: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fwd_ret_24: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fwd_max_favorable_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fwd_max_adverse_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fwd_data_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ledger_entry = relationship("ReviewLedger", backref="forward_outcome")
