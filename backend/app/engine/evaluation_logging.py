"""Helpers for persistent symbol evaluation logs."""

from __future__ import annotations

from typing import Any

from app.models.symbol_evaluation_log import SymbolEvaluationLog


def build_symbol_evaluation_log(
    *,
    strategy_id: str,
    cycle_id: str,
    symbol: str,
    stage: str,
    status: str,
    reason_code: str | None = None,
    reason_text: str | None = None,
    metrics_json: dict[str, Any] | None = None,
    context_json: dict[str, Any] | None = None,
) -> SymbolEvaluationLog:
    return SymbolEvaluationLog(
        strategy_id=strategy_id,
        cycle_id=cycle_id,
        symbol=symbol,
        stage=stage,
        status=status,
        reason_code=reason_code,
        reason_text=reason_text,
        metrics_json=metrics_json or {},
        context_json=context_json or {},
    )
