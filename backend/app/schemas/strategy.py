"""Pydantic schemas for strategy endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None


class StrategyResponse(BaseModel):
    id: str
    name: str
    description: str | None
    config_json: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyWithStats(StrategyResponse):
    available_usdt: float | None = None
    initial_balance_usdt: float | None = None
    total_equity: float | None = None
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
