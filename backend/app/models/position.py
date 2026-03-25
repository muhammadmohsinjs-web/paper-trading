from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import PositionSide
from app.models.mixins import UUIDPrimaryKeyMixin


class Position(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("strategy_id", "symbol", name="uq_positions_strategy_symbol"),)

    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    side: Mapped[PositionSide] = mapped_column(Enum(PositionSide), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    entry_fee: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False, default=Decimal("0"))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    stop_loss_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 12), nullable=True, default=None,
    )
    take_profit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 12), nullable=True, default=None,
    )
    trailing_stop_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 12), nullable=True, default=None,
    )
    entry_atr: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 12), nullable=True, default=None,
    )
    entry_confidence_raw: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True, default=None,
    )
    entry_confidence_final: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True, default=None,
    )
    entry_confidence_bucket: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, default=None,
    )

    strategy = relationship("Strategy", back_populates="positions")
