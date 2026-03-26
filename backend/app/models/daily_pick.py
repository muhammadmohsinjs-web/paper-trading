from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class DailyPick(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "daily_picks"
    __table_args__ = (
        UniqueConstraint("strategy_id", "selection_date", "rank", name="uq_daily_picks_strategy_date_rank"),
        UniqueConstraint("strategy_id", "selection_date", "symbol", name="uq_daily_picks_strategy_date_symbol"),
    )

    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selection_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regime: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    setup_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    recommended_strategy: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    strategy = relationship("Strategy", back_populates="daily_picks")
