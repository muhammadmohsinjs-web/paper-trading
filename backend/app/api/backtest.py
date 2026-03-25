"""Backtesting API endpoints."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.backtest.engine import BacktestEngine, BacktestReport
from app.strategies.registry import list_strategies

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backtest", tags=["backtest"])

# In-memory store for backtest results (replace with DB in production)
_backtest_results: dict[str, dict[str, Any]] = {}
_backtest_tasks: dict[str, asyncio.Task] = {}


class BacktestRequest(BaseModel):
    strategy_type: str
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    start_time_ms: int
    end_time_ms: int
    initial_balance: float = 1000.0
    config: dict[str, Any] | None = None


class CompareRequest(BaseModel):
    strategies: list[str]
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    start_time_ms: int
    end_time_ms: int
    initial_balance: float = 1000.0


@router.post("/run")
async def run_backtest(request: BacktestRequest):
    """Start a backtest run. Returns a job ID to poll for results."""
    if request.strategy_type not in list_strategies():
        raise HTTPException(400, f"Unknown strategy: {request.strategy_type}")

    job_id = str(uuid4())
    _backtest_results[job_id] = {"status": "running", "strategy_type": request.strategy_type}

    async def _run():
        try:
            engine = BacktestEngine()
            report = await engine.run(
                strategy_type=request.strategy_type,
                symbol=request.symbol,
                start_time_ms=request.start_time_ms,
                end_time_ms=request.end_time_ms,
                interval=request.interval,
                initial_balance=request.initial_balance,
                config=request.config,
            )
            _backtest_results[job_id] = {
                "status": "completed",
                **report.to_dict(),
                "equity_curve": report.equity_curve,
                "regime_history": report.regime_history,
                "trades": [asdict(t) for t in report.trades],
            }
        except Exception as e:
            logger.exception("Backtest failed job_id=%s", job_id)
            _backtest_results[job_id] = {
                "status": "failed",
                "error": str(e),
                "strategy_type": request.strategy_type,
            }

    task = asyncio.create_task(_run())
    _backtest_tasks[job_id] = task

    return {"job_id": job_id, "status": "running"}


@router.get("/{job_id}")
async def get_backtest_result(job_id: str):
    """Get the status/results of a backtest run."""
    result = _backtest_results.get(job_id)
    if result is None:
        raise HTTPException(404, f"Backtest job not found: {job_id}")

    # For large results, strip equity curve and trades from status check
    if result.get("status") == "completed":
        summary = {k: v for k, v in result.items() if k not in ("equity_curve", "trades")}
        summary["equity_curve_length"] = len(result.get("equity_curve", []))
        summary["trades_count"] = len(result.get("trades", []))
        return summary
    return result


@router.get("/{job_id}/equity-curve")
async def get_backtest_equity_curve(job_id: str):
    """Get equity curve data from a completed backtest."""
    result = _backtest_results.get(job_id)
    if result is None:
        raise HTTPException(404, f"Backtest job not found: {job_id}")
    if result.get("status") != "completed":
        raise HTTPException(400, f"Backtest not completed: {result.get('status')}")

    return {
        "job_id": job_id,
        "equity_curve": result.get("equity_curve", []),
    }


@router.get("/{job_id}/trades")
async def get_backtest_trades(job_id: str):
    """Get all trades from a completed backtest."""
    result = _backtest_results.get(job_id)
    if result is None:
        raise HTTPException(404, f"Backtest job not found: {job_id}")
    if result.get("status") != "completed":
        raise HTTPException(400, f"Backtest not completed: {result.get('status')}")

    return {
        "job_id": job_id,
        "trades": result.get("trades", []),
    }


@router.post("/compare")
async def compare_strategies(request: CompareRequest):
    """Run backtests for multiple strategies and compare results."""
    available = list_strategies()
    for s in request.strategies:
        if s not in available:
            raise HTTPException(400, f"Unknown strategy: {s}")

    engine = BacktestEngine()
    results: dict[str, Any] = {}

    for strategy_type in request.strategies:
        try:
            report = await engine.run(
                strategy_type=strategy_type,
                symbol=request.symbol,
                start_time_ms=request.start_time_ms,
                end_time_ms=request.end_time_ms,
                interval=request.interval,
                initial_balance=request.initial_balance,
            )
            results[strategy_type] = {
                "metrics": asdict(report.metrics),
                "total_candles": report.total_candles,
                "equity_curve_length": len(report.equity_curve),
            }
        except Exception as e:
            logger.exception("Compare backtest failed for %s", strategy_type)
            results[strategy_type] = {"error": str(e)}

    # Rank by Sharpe ratio
    ranked = sorted(
        [
            (st, r)
            for st, r in results.items()
            if "metrics" in r
        ],
        key=lambda x: x[1]["metrics"].get("sharpe_ratio", 0),
        reverse=True,
    )

    return {
        "symbol": request.symbol,
        "interval": request.interval,
        "initial_balance": request.initial_balance,
        "results": results,
        "ranking": [
            {
                "rank": i + 1,
                "strategy": st,
                "sharpe_ratio": r["metrics"]["sharpe_ratio"],
                "total_pnl_pct": r["metrics"]["total_pnl_pct"],
                "win_rate": r["metrics"]["win_rate"],
                "max_drawdown_pct": r["metrics"]["max_drawdown_pct"],
            }
            for i, (st, r) in enumerate(ranked)
        ],
    }
