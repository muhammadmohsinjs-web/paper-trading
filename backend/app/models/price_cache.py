from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, Numeric, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PriceCache(Base):
    __tablename__ = "price_cache"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "interval", "open_time", name="pk_price_cache"),
    )

    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    open_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
