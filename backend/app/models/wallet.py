from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, UpdatedAtMixin


class Wallet(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "wallets"

    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    initial_balance_usdt: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("1000"),
    )
    available_usdt: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("1000"),
    )
    peak_equity_usdt: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("1000"),
    )
    daily_loss_usdt: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("0"),
    )
    daily_loss_reset_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        default=lambda: datetime.now(timezone.utc).date(),
    )
    weekly_loss_usdt: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("0"),
    )
    weekly_loss_reset_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        default=lambda: datetime.now(timezone.utc).date(),
    )

    strategy = relationship("Strategy", back_populates="wallet")
