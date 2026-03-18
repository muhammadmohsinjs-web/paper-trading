"""Pydantic schemas for dashboard endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.strategy import StrategyWithStats


class DashboardResponse(BaseModel):
    strategies: list[StrategyWithStats]
    total_strategies: int
    active_strategies: int
    ai_enabled_strategies: int = 0
    ai_total_calls: int = 0
    ai_total_cost_usdt: float = 0.0


class LeaderboardEntry(BaseModel):
    strategy_id: str
    strategy_name: str
    total_pnl: float
    win_rate: float
    total_trades: int
    total_equity: float
    ai_enabled: bool = False
    ai_total_calls: int = 0
    ai_total_cost_usdt: float = 0.0
    rank: int


class EquityPoint(BaseModel):
    timestamp: datetime
    total_equity_usdt: float
