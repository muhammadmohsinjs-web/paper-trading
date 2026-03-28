from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, UpdatedAtMixin


class Strategy(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="single_symbol")
    primary_symbol: Mapped[str] = mapped_column(String(24), nullable=False, default="BTCUSDT")
    scan_universe_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    top_pick_count: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    selection_hour_utc: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrent_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="anthropic")
    ai_strategy_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ai_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    ai_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=700)
    ai_temperature: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("0.2"))
    ai_last_decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_last_decision_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ai_last_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_last_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ai_last_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ai_last_prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_last_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_last_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_last_cost_usdt: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0"))
    ai_total_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_total_prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_total_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_total_cost_usdt: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0"))

    # Risk management
    stop_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("3.0"))
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("15.0"))
    risk_per_trade_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("2.0"))
    max_position_size_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("30.0"))
    candle_interval: Mapped[str] = mapped_column(String(8), nullable=False, default="1h")
    consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_consecutive_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_size_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("1.0"))

    # Re-entry cooldown after stop-loss
    last_stop_loss_symbol: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    last_stop_loss_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet = relationship(
        "Wallet",
        back_populates="strategy",
        uselist=False,
        cascade="all, delete-orphan",
    )
    positions = relationship(
        "Position",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )
    trades = relationship(
        "Trade",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )
    snapshots = relationship(
        "Snapshot",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )
    daily_picks = relationship(
        "DailyPick",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="DailyPick.rank",
    )
    symbol_ownerships = relationship(
        "SymbolOwnership",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )
