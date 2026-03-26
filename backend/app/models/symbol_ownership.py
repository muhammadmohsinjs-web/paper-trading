from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class SymbolOwnership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "symbol_ownership"

    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_name: Mapped[str] = mapped_column(String(120), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    release_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    assignment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    assignment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    strategy = relationship("Strategy", back_populates="symbol_ownerships")
