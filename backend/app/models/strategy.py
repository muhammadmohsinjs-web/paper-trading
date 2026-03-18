from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, UpdatedAtMixin


class Strategy(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
