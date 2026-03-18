from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
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

    strategy = relationship("Strategy", back_populates="wallet")
