"""Pydantic schemas for strategy endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

AIProvider = Literal["anthropic", "openai"]


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False
    ai_enabled: bool = False
    ai_provider: AIProvider | None = None
    ai_strategy_key: str | None = None
    ai_model: str | None = None
    ai_cooldown_seconds: int | None = None
    ai_max_tokens: int | None = None
    ai_temperature: float | None = None
    stop_loss_pct: float | None = None
    max_drawdown_pct: float | None = None
    risk_per_trade_pct: float | None = None
    max_position_size_pct: float | None = None
    candle_interval: str | None = None


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None
    ai_enabled: bool | None = None
    ai_provider: AIProvider | None = None
    ai_strategy_key: str | None = None
    ai_model: str | None = None
    ai_cooldown_seconds: int | None = None
    ai_max_tokens: int | None = None
    ai_temperature: float | None = None
    stop_loss_pct: float | None = None
    max_drawdown_pct: float | None = None
    risk_per_trade_pct: float | None = None
    max_position_size_pct: float | None = None
    candle_interval: str | None = None


class StrategyResponse(BaseModel):
    id: str
    name: str
    description: str | None
    config_json: dict[str, Any]
    is_active: bool
    ai_enabled: bool = False
    ai_provider: AIProvider = "anthropic"
    ai_strategy_key: str | None = None
    ai_model: str | None = None
    ai_cooldown_seconds: int = 60
    ai_max_tokens: int = 700
    ai_temperature: float = 0.2
    ai_last_decision_at: datetime | None = None
    ai_last_decision_status: str | None = None
    ai_last_reasoning: str | None = None
    ai_last_provider: AIProvider | None = None
    ai_last_model: str | None = None
    ai_last_prompt_tokens: int = 0
    ai_last_completion_tokens: int = 0
    ai_last_total_tokens: int = 0
    ai_last_cost_usdt: float = 0.0
    ai_total_calls: int = 0
    ai_total_prompt_tokens: int = 0
    ai_total_completion_tokens: int = 0
    ai_total_tokens: int = 0
    ai_total_cost_usdt: float = 0.0
    stop_loss_pct: float = 3.0
    max_drawdown_pct: float = 15.0
    risk_per_trade_pct: float = 2.0
    max_position_size_pct: float = 30.0
    candle_interval: str = "1h"
    consecutive_losses: int = 0
    max_consecutive_losses: int = 0
    streak_size_multiplier: float = 1.0
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
    unrealized_pnl: float = 0.0
    has_open_position: bool = False
    win_rate: float = 0.0
