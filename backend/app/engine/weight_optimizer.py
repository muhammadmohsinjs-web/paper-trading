"""Adaptive composite weight optimization.

Adjusts indicator weights based on which votes have been most predictive
in recent trades. Votes that correctly predicted profitable trades get
increased weight; votes that predicted incorrectly get decreased weight.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MIN_TRADES_FOR_ADAPTATION = 20  # Don't adapt with too few trades


def compute_adaptive_weights(
    trade_history: list[dict[str, Any]],
    base_weights: dict[str, float],
    learning_rate: float = 0.3,
) -> dict[str, float]:
    """Compute adapted weights from trade history.

    Args:
        trade_history: Recent trades with 'indicator_snapshot' containing
            vote values, and 'pnl' for outcome.
        base_weights: Default weights to blend with learned weights.
        learning_rate: How much to adjust (0=ignore history, 1=fully adaptive).

    Returns:
        Normalized weight dict.
    """
    if len(trade_history) < MIN_TRADES_FOR_ADAPTATION:
        return base_weights.copy()

    vote_keys = list(base_weights.keys())
    accuracy: dict[str, list[bool]] = {key: [] for key in vote_keys}

    for trade in trade_history:
        snapshot = trade.get("indicator_snapshot") or {}
        pnl = trade.get("pnl")
        if pnl is None:
            continue

        profitable = float(pnl) > 0

        # Check which votes agreed with the trade outcome
        votes = snapshot.get("votes") or {}
        trade_side = trade.get("side", "BUY")

        for key in vote_keys:
            vote_value = votes.get(key)
            if vote_value is None:
                continue

            if trade_side == "BUY":
                # For a BUY trade, a positive vote was the prediction
                predicted_profit = float(vote_value) > 0
            else:
                # For a SELL, a negative vote was the prediction
                predicted_profit = float(vote_value) < 0

            correct = predicted_profit == profitable
            accuracy[key].append(correct)

    # Compute win rates per vote
    vote_win_rates: dict[str, float] = {}
    for key in vote_keys:
        if accuracy[key]:
            vote_win_rates[key] = sum(accuracy[key]) / len(accuracy[key])
        else:
            vote_win_rates[key] = 0.5  # neutral

    # Blend base weights with performance-adjusted weights
    adapted: dict[str, float] = {}
    for key in vote_keys:
        base = base_weights.get(key, 0.0)
        win_rate = vote_win_rates.get(key, 0.5)
        # Scale: 50% win rate = 1.0x, 70% = 1.4x, 30% = 0.6x
        performance_multiplier = 0.2 + 1.6 * win_rate
        adapted_weight = base * (1 - learning_rate) + base * performance_multiplier * learning_rate
        adapted[key] = max(0.05, adapted_weight)  # Floor at 5% to keep all indicators active

    # Normalize
    total = sum(adapted.values())
    if total > 0:
        return {key: value / total for key, value in adapted.items()}

    return base_weights.copy()
