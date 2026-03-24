"""Pydantic schemas for trade endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TradeResponse(BaseModel):
    id: str
    strategy_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    market_price: float
    fee: float
    slippage: float
    pnl: float | None
    pnl_pct: float | None
    ai_reasoning: str | None
    strategy_name: str | None = None
    strategy_type: str | None = None
    decision_source: str | None = None
    indicator_snapshot: dict | None = None
    cost_usdt: float | None = None
    composite_score: float | None = None
    composite_confidence: float | None = None
    wallet_balance_before: float | None = None
    wallet_balance_after: float | None = None
    executed_at: datetime

    model_config = {"from_attributes": True}


class TradeSummary(BaseModel):
    total_trades: int
    buy_count: int
    sell_count: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    best_trade: float
    worst_trade: float


class TradeLogResponse(BaseModel):
    total: int
    offset: int
    limit: int
    trades: list[TradeResponse]
