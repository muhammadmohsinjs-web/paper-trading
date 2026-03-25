"""Pydantic schemas for wallet data."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class WalletResponse(BaseModel):
    id: str
    strategy_id: str
    initial_balance_usdt: float
    available_usdt: float
    peak_equity_usdt: float
    daily_loss_usdt: float
    daily_loss_reset_date: date | None = None
    weekly_loss_usdt: float
    weekly_loss_reset_date: date | None = None
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
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    trailing_stop_price: float | None = None
    entry_atr: float | None = None
    entry_confidence_raw: float | None = None
    entry_confidence_final: float | None = None
    entry_confidence_bucket: str | None = None
    current_price: float | None = None
    unrealized_pnl: float | None = None

    model_config = {"from_attributes": True}
