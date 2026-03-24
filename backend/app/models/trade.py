from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base
from app.models.enums import TradeSide
from app.models.mixins import UUIDPrimaryKeyMixin


class Trade(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "trades"

    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    side: Mapped[TradeSide] = mapped_column(Enum(TradeSide), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    market_price: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False, default=Decimal("0"))
    slippage: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False, default=Decimal("0"))
    pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 12), nullable=True)
    pnl_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Trade log context fields ──────────────────────────────────────
    strategy_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    strategy_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # rule, ai, hybrid_entry, hybrid_exit, risk
    indicator_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # RSI, MACD, SMA, etc. at trade time
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    composite_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    cost_usdt: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)  # total USDT spent (BUY) or received (SELL)
    wallet_balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    wallet_balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    strategy = relationship("Strategy", back_populates="trades")
