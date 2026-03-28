"""Scanner performance stats — tracks win rate by symbol + family + regime + side."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class ScannerPerfStats(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scanner_perf_stats"
    __table_args__ = (
        UniqueConstraint("symbol", "setup_family", "detailed_regime", "side", name="uq_scanner_perf_key"),
    )

    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    setup_family: Mapped[str] = mapped_column(String(32), nullable=False)
    detailed_regime: Mapped[str] = mapped_column(String(48), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # "BUY" or "SELL"
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_hold_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
