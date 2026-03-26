"""Centralized trade-quality thresholds and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings

SETTINGS = get_settings()


def _resolve_float(config: dict[str, Any] | None, key: str, default: float) -> float:
    value = (config or {}).get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TradeQualityThresholds:
    min_atr_pct: float
    min_range_pct_20: float
    min_range_pct_24h: float
    min_abs_change_pct_24h: float
    min_close_std_pct_24h: float
    min_market_quality_score: float
    min_move_vs_cost_multiple: float
    min_directional_score: float
    min_movement_quality_score: float
    min_composite_market_quality_score: float
    min_edge_strength: float
    min_reward_to_cost_ratio: float
    min_gross_reward_cost_multiple: float
    min_net_reward_pct: float
    min_net_rr: float
    min_stop_distance_pct: float
    min_take_profit_distance_pct: float
    stablecoin_base_denylist: frozenset[str]


def resolve_trade_quality_thresholds(config: dict[str, Any] | None = None) -> TradeQualityThresholds:
    configured_denylist = (config or {}).get("stablecoin_base_denylist")
    if isinstance(configured_denylist, list):
        denylist = frozenset(str(item).upper() for item in configured_denylist if str(item).strip())
    else:
        denylist = frozenset(str(item).upper() for item in SETTINGS.stablecoin_base_denylist)

    return TradeQualityThresholds(
        min_atr_pct=_resolve_float(config, "trade_quality_min_atr_pct", SETTINGS.trade_quality_min_atr_pct),
        min_range_pct_20=_resolve_float(config, "trade_quality_min_range_pct_20", SETTINGS.trade_quality_min_range_pct_20),
        min_range_pct_24h=_resolve_float(config, "trade_quality_min_range_pct_24h", SETTINGS.trade_quality_min_range_pct_24h),
        min_abs_change_pct_24h=_resolve_float(config, "trade_quality_min_abs_change_pct_24h", SETTINGS.trade_quality_min_abs_change_pct_24h),
        min_close_std_pct_24h=_resolve_float(config, "trade_quality_min_close_std_pct_24h", SETTINGS.trade_quality_min_close_std_pct_24h),
        min_market_quality_score=_resolve_float(config, "trade_quality_min_market_quality_score", SETTINGS.trade_quality_min_market_quality_score),
        min_move_vs_cost_multiple=_resolve_float(config, "trade_quality_min_move_vs_cost_multiple", SETTINGS.trade_quality_min_move_vs_cost_multiple),
        min_directional_score=_resolve_float(config, "trade_quality_min_directional_score", SETTINGS.trade_quality_min_directional_score),
        min_movement_quality_score=_resolve_float(config, "trade_quality_min_movement_quality_score", SETTINGS.trade_quality_min_movement_quality_score),
        min_composite_market_quality_score=_resolve_float(config, "trade_quality_min_composite_market_quality_score", SETTINGS.trade_quality_min_composite_market_quality_score),
        min_edge_strength=_resolve_float(config, "trade_quality_min_edge_strength", SETTINGS.trade_quality_min_edge_strength),
        min_reward_to_cost_ratio=_resolve_float(config, "trade_quality_min_reward_to_cost_ratio", SETTINGS.trade_quality_min_reward_to_cost_ratio),
        min_gross_reward_cost_multiple=_resolve_float(config, "trade_quality_min_gross_reward_cost_multiple", SETTINGS.trade_quality_min_gross_reward_cost_multiple),
        min_net_reward_pct=_resolve_float(config, "trade_quality_min_net_reward_pct", SETTINGS.trade_quality_min_net_reward_pct),
        min_net_rr=_resolve_float(config, "trade_quality_min_net_rr", SETTINGS.trade_quality_min_net_rr),
        min_stop_distance_pct=_resolve_float(config, "trade_quality_min_stop_distance_pct", SETTINGS.trade_quality_min_stop_distance_pct),
        min_take_profit_distance_pct=_resolve_float(config, "trade_quality_min_take_profit_distance_pct", SETTINGS.trade_quality_min_take_profit_distance_pct),
        stablecoin_base_denylist=denylist,
    )
