"""Performance metrics for backtesting — Sharpe, Sortino, expectancy, etc."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class BacktestMetrics:
    """All computed performance metrics from a backtest run."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_hours: float = 0.0
    avg_trade_duration_hours: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    annualized_return_pct: float = 0.0


@dataclass
class SimulatedTrade:
    """Single trade record from a backtest."""

    side: str  # "BUY" or "SELL"
    symbol: str
    quantity: float
    entry_price: float
    exit_price: float | None = None
    entry_time: int = 0  # ms timestamp
    exit_time: int | None = None  # ms timestamp
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fee: float = 0.0
    reason: str = ""


def compute_metrics(
    trades: list[SimulatedTrade],
    equity_curve: list[tuple[int, float]],
    initial_balance: float,
    periods_per_year: int = 8760,  # hourly candles in a year
) -> BacktestMetrics:
    """Compute all performance metrics from backtest results.

    Args:
        trades: List of completed (closed) trades with PnL.
        equity_curve: List of (timestamp_ms, equity_value) tuples.
        initial_balance: Starting capital.
        periods_per_year: Number of periods in a year (8760 for hourly).
    """
    # Filter to sell trades (completed round-trips with PnL)
    closed_trades = [t for t in trades if t.side == "SELL" and t.exit_price is not None]
    total_trades = len(closed_trades)

    if total_trades == 0:
        return BacktestMetrics()

    pnls = [t.pnl for t in closed_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    total_pnl = sum(pnls)
    total_pnl_pct = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0.0

    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    largest_win = max(wins) if wins else 0.0
    largest_loss = min(losses) if losses else 0.0

    # Profit Factor
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    # Expectancy
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    # Returns from equity curve
    if len(equity_curve) >= 2:
        equities = [e[1] for e in equity_curve]
        returns = []
        for i in range(1, len(equities)):
            if equities[i - 1] > 0:
                returns.append((equities[i] - equities[i - 1]) / equities[i - 1])
            else:
                returns.append(0.0)
        returns_arr = np.array(returns)
    else:
        returns_arr = np.array([0.0])

    # Sharpe Ratio (annualized)
    mean_return = float(np.mean(returns_arr))
    std_return = float(np.std(returns_arr, ddof=1)) if len(returns_arr) > 1 else 0.0
    sharpe_ratio = (
        (mean_return / std_return * math.sqrt(periods_per_year))
        if std_return > 0
        else 0.0
    )

    # Sortino Ratio (annualized, downside deviation only)
    downside_returns = returns_arr[returns_arr < 0]
    downside_std = (
        float(np.std(downside_returns, ddof=1))
        if len(downside_returns) > 1
        else 0.0
    )
    sortino_ratio = (
        (mean_return / downside_std * math.sqrt(periods_per_year))
        if downside_std > 0
        else 0.0
    )

    # Max Drawdown
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    max_drawdown_duration_hours = 0.0
    if equity_curve:
        equities = [e[1] for e in equity_curve]
        timestamps = [e[0] for e in equity_curve]
        peak = equities[0]
        peak_time = timestamps[0]
        dd_start_time = timestamps[0]

        for i, eq in enumerate(equities):
            if eq > peak:
                peak = eq
                peak_time = timestamps[i]
                dd_start_time = timestamps[i]
            dd = peak - eq
            dd_pct = dd / peak * 100 if peak > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd
                max_drawdown_pct = dd_pct
                max_drawdown_duration_hours = (timestamps[i] - dd_start_time) / 3_600_000

    # Calmar Ratio
    total_hours = 0
    if len(equity_curve) >= 2:
        total_hours = (equity_curve[-1][0] - equity_curve[0][0]) / 3_600_000
    total_years = total_hours / 8760 if total_hours > 0 else 1.0
    annualized_return_pct = (total_pnl_pct / total_years) if total_years > 0 else 0.0
    calmar_ratio = (
        (annualized_return_pct / max_drawdown_pct)
        if max_drawdown_pct > 0
        else 0.0
    )

    # Trade duration
    durations = []
    for t in closed_trades:
        if t.entry_time and t.exit_time:
            durations.append((t.exit_time - t.entry_time) / 3_600_000)
    avg_trade_duration_hours = float(np.mean(durations)) if durations else 0.0

    # Consecutive wins/losses
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0
    for p in pnls:
        if p > 0:
            current_wins += 1
            current_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, current_wins)
        elif p < 0:
            current_losses += 1
            current_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate, 4),
        total_pnl=round(total_pnl, 4),
        total_pnl_pct=round(total_pnl_pct, 4),
        avg_win=round(avg_win, 4),
        avg_loss=round(avg_loss, 4),
        largest_win=round(largest_win, 4),
        largest_loss=round(largest_loss, 4),
        profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else 999.99,
        expectancy=round(expectancy, 4),
        sharpe_ratio=round(sharpe_ratio, 4),
        sortino_ratio=round(sortino_ratio, 4),
        calmar_ratio=round(calmar_ratio, 4),
        max_drawdown=round(max_drawdown, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        max_drawdown_duration_hours=round(max_drawdown_duration_hours, 2),
        avg_trade_duration_hours=round(avg_trade_duration_hours, 2),
        max_consecutive_losses=max_consecutive_losses,
        max_consecutive_wins=max_consecutive_wins,
        annualized_return_pct=round(annualized_return_pct, 4),
    )
