from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class AICallLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_call_logs"

    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, default="BTCUSDT")
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # signal, hold, skipped, error
    skip_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # flat_market, cooldown, missing_api_key
    action: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # buy, sell, hold
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3), nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usdt: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    strategy = relationship("Strategy", backref="ai_call_logs")
