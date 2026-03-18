"""Pydantic schemas for wallet data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WalletResponse(BaseModel):
    id: str
    strategy_id: str
    initial_balance_usdt: float
    available_usdt: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    id: str
    strategy_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_fee: float
    opened_at: datetime
    current_price: float | None = None
    unrealized_pnl: float | None = None

    model_config = {"from_attributes": True}
