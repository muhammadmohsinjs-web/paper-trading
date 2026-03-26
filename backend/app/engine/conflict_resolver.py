from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.engine.reason_codes import (
    CONFLICT_LOST_HIGHER_SCORE,
    CONFLICT_LOST_TIEBREAK,
    COOLDOWN_ACTIVE,
    GLOBAL_MAX_REACHED,
    MAX_PICKS_REACHED,
    PINNED_TO_OTHER_STRATEGY,
)
from app.engine.strategy_scorer import StrategyCandidate, StrategyRejection, normalize_strategy_type


TIEBREAK_PRIORITY = {
    "hybrid_composite": 0,
    "hybrid_ai_composite": 0,
    "macd_momentum": 1,
    "sma_crossover": 2,
    "bollinger_bounce": 3,
    "rsi_mean_reversion": 4,
}


@dataclass(frozen=True)
class PinnedSymbol:
    strategy_id: str
    strategy_name: str
    strategy_type: str
    symbol: str
    assignment_reason: str = "Pinned open position"
    final_score: float = 1.0
    regime: str = "pinned"
    setup_type: str = "open_position"
    recommended_strategy: str = ""
    setup_fit_score: float = 1.0
    regime_fit_score: float = 1.0
    liquidity_score: float = 1.0
    perf_memory_score: float = 0.5
    vol_quality_score: float = 0.5
    expected_rr_score: float = 0.5
    liquidity_usdt: float = 0.0
    market_quality_score: float = 0.0
    reward_to_cost_ratio: float = 0.0


def resolve_conflicts(
    strategy_candidates: dict[str, list[StrategyCandidate]],
    pinned_symbols: dict[str, PinnedSymbol],
    cooldowns: dict[tuple[str, str], datetime],
    per_strategy_max: dict[str, int],
    global_max: int,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, list[StrategyCandidate]], list[StrategyRejection]]:
    current_time = now or datetime.utcnow()
    assignments: dict[str, list[StrategyCandidate]] = {strategy_id: [] for strategy_id in strategy_candidates}
    rejections: list[StrategyRejection] = []
    assigned_symbols: set[str] = set()
    strategy_counts = {strategy_id: 0 for strategy_id in strategy_candidates}

    for symbol, pin in pinned_symbols.items():
        candidate = StrategyCandidate(
            strategy_id=pin.strategy_id,
            strategy_name=pin.strategy_name,
            strategy_type=normalize_strategy_type(pin.strategy_type),
            symbol=symbol,
            final_score=pin.final_score,
            regime=pin.regime,
            setup_type=pin.setup_type,
            recommended_strategy=normalize_strategy_type(pin.recommended_strategy or pin.strategy_type),
            assignment_reason=pin.assignment_reason,
            setup_fit_score=pin.setup_fit_score,
            regime_fit_score=pin.regime_fit_score,
            liquidity_score=pin.liquidity_score,
            perf_memory_score=pin.perf_memory_score,
            vol_quality_score=pin.vol_quality_score,
            expected_rr_score=pin.expected_rr_score,
            liquidity_usdt=pin.liquidity_usdt,
            market_quality_score=pin.market_quality_score,
            reward_to_cost_ratio=pin.reward_to_cost_ratio,
            movement_quality={},
        )
        assignments.setdefault(candidate.strategy_id, []).append(candidate)
        assigned_symbols.add(symbol)
        strategy_counts[candidate.strategy_id] = strategy_counts.get(candidate.strategy_id, 0) + 1

    claim_pool: list[StrategyCandidate] = []
    claim_counts: dict[str, int] = {}
    winners_by_symbol: dict[str, StrategyCandidate] = {}

    for candidates in strategy_candidates.values():
        for candidate in candidates:
            claim_counts[candidate.symbol] = claim_counts.get(candidate.symbol, 0) + 1
            if candidate.symbol in pinned_symbols and pinned_symbols[candidate.symbol].strategy_id != candidate.strategy_id:
                rejections.append(_build_rejection(candidate, PINNED_TO_OTHER_STRATEGY, "Symbol is pinned to another strategy"))
                continue
            cooldown_until = cooldowns.get((candidate.strategy_id, candidate.symbol))
            if cooldown_until is not None and cooldown_until > current_time:
                rejections.append(_build_rejection(candidate, COOLDOWN_ACTIVE, "Cooldown is still active for this symbol"))
                continue
            claim_pool.append(candidate)

    claim_pool.sort(
        key=lambda item: (
            -item.final_score,
            -item.regime_fit_score,
            -item.perf_memory_score,
            -item.expected_rr_score,
            TIEBREAK_PRIORITY.get(normalize_strategy_type(item.strategy_type), 99),
        )
    )

    for candidate in claim_pool:
        if len(assigned_symbols) >= global_max:
            rejections.append(_build_rejection(candidate, GLOBAL_MAX_REACHED, "Global symbol cap reached"))
            continue
        if strategy_counts.get(candidate.strategy_id, 0) >= per_strategy_max.get(candidate.strategy_id, 1):
            rejections.append(_build_rejection(candidate, MAX_PICKS_REACHED, "Per-strategy pick cap reached"))
            continue
        existing = winners_by_symbol.get(candidate.symbol)
        if candidate.symbol in assigned_symbols:
            winner = existing or next(
                (item for items in assignments.values() for item in items if item.symbol == candidate.symbol),
                None,
            )
            reason_code = _conflict_reason(candidate, winner)
            rejections.append(_build_rejection(candidate, reason_code, "Another strategy already won this symbol"))
            continue

        winners_by_symbol[candidate.symbol] = candidate
        assignments.setdefault(candidate.strategy_id, []).append(candidate)
        assigned_symbols.add(candidate.symbol)
        strategy_counts[candidate.strategy_id] = strategy_counts.get(candidate.strategy_id, 0) + 1

    for strategy_id, items in assignments.items():
        items.sort(key=lambda item: item.final_score, reverse=True)
        assignments[strategy_id] = items

    return assignments, rejections


def _conflict_reason(candidate: StrategyCandidate, winner: StrategyCandidate | None) -> str:
    if winner is None:
        return CONFLICT_LOST_HIGHER_SCORE
    if abs(candidate.final_score - winner.final_score) < 1e-9:
        return CONFLICT_LOST_TIEBREAK
    return CONFLICT_LOST_HIGHER_SCORE


def _build_rejection(candidate: StrategyCandidate, reason_code: str, reason_text: str) -> StrategyRejection:
    return StrategyRejection(
        strategy_id=candidate.strategy_id,
        strategy_name=candidate.strategy_name,
        strategy_type=candidate.strategy_type,
        symbol=candidate.symbol,
        reason_code=reason_code,
        reason_text=reason_text,
        setup_type=candidate.setup_type,
        regime=candidate.regime,
    )
