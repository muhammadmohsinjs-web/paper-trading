"""Backtesting engine — walks forward through historical candles and executes strategy signals."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any

from app.backtest.data_loader import HistoricalCandle, fetch_historical_candles
from app.backtest.metrics import BacktestMetrics, SimulatedTrade, compute_metrics
from app.backtest.simulated_wallet import SimulatedWallet
from app.engine.fee_model import calculate_fee, SPOT_FEE_RATE
from app.engine.slippage import apply_slippage
from app.market.indicators import compute_indicators
from app.models.enums import TradeSide
from app.regime.classifier import RegimeClassifier
from app.regime.types import RegimeResult
from app.strategies.base import BaseStrategy
from app.strategies.registry import get_strategy_class

logger = logging.getLogger(__name__)

MIN_CANDLES = 50


@dataclass
class BacktestReport:
    """Complete results of a backtest run."""

    strategy_type: str
    symbol: str
    interval: str
    initial_balance: float
    start_time_ms: int
    end_time_ms: int
    total_candles: int
    trades: list[SimulatedTrade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    regime_history: list[dict[str, Any]] = field(default_factory=list)
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_type": self.strategy_type,
            "symbol": self.symbol,
            "interval": self.interval,
            "initial_balance": self.initial_balance,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "total_candles": self.total_candles,
            "total_trades": len([t for t in self.trades if t.side == "SELL"]),
            "equity_curve_length": len(self.equity_curve),
            "metrics": asdict(self.metrics),
        }


class BacktestEngine:
    """Walk-forward backtesting engine.

    Replays historical candles through a strategy's decide() method
    and simulates trades with realistic fees and slippage.
    """

    def __init__(
        self,
        fee_rate: Decimal = SPOT_FEE_RATE,
        deterministic_slippage: bool = True,
    ):
        self.fee_rate = fee_rate
        self.deterministic_slippage = deterministic_slippage
        self.regime_classifier = RegimeClassifier()

    async def run(
        self,
        strategy_type: str,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        interval: str = "1h",
        initial_balance: float = 1000.0,
        config: dict[str, Any] | None = None,
    ) -> BacktestReport:
        """Run a full backtest.

        Args:
            strategy_type: One of the registered strategy types.
            symbol: Trading pair (e.g., "BTCUSDT").
            start_time_ms: Start timestamp in milliseconds.
            end_time_ms: End timestamp in milliseconds.
            interval: Candle interval (e.g., "1h", "4h").
            initial_balance: Starting capital in USDT.
            config: Strategy configuration overrides.
        """
        # Fetch data
        candles = await fetch_historical_candles(
            symbol, interval, start_time_ms, end_time_ms
        )

        if len(candles) < MIN_CANDLES:
            logger.warning(
                "Insufficient candles for backtest: %d < %d", len(candles), MIN_CANDLES
            )
            return BacktestReport(
                strategy_type=strategy_type,
                symbol=symbol,
                interval=interval,
                initial_balance=initial_balance,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                total_candles=len(candles),
            )

        # Initialize
        strategy_cls = get_strategy_class(strategy_type)
        strategy = strategy_cls()
        wallet = SimulatedWallet(initial_balance_usdt=Decimal(str(initial_balance)))
        cfg = config or {}

        trades: list[SimulatedTrade] = []
        equity_curve: list[tuple[int, float]] = []
        regime_history: list[dict[str, Any]] = []
        pending_buy: SimulatedTrade | None = None

        # Walk forward
        for i in range(MIN_CANDLES, len(candles)):
            window = candles[: i + 1]
            current = window[-1]

            closes = [c.close for c in window]
            highs = [c.high for c in window]
            lows = [c.low for c in window]
            volumes = [c.volume for c in window]

            # Compute indicators
            indicators = compute_indicators(
                closes, cfg, highs=highs, lows=lows, volumes=volumes
            )

            # Detect regime
            regime_result = self.regime_classifier.classify(indicators)
            if i % 24 == 0:  # Log regime every 24 candles
                regime_history.append({
                    "time": current.open_time,
                    "regime": regime_result.regime.value,
                    "confidence": round(regime_result.confidence, 3),
                })

            # Get position state
            position = wallet.get_position(symbol)
            has_position = position is not None

            # Strategy decision
            signal = strategy.decide(
                indicators, has_position, wallet.available_usdt
            )

            # Execute signal
            if signal is not None:
                market_price = Decimal(str(current.close))

                if signal.action == TradeSide.BUY and not has_position:
                    trade = self._execute_buy(
                        wallet, symbol, market_price,
                        signal.quantity_pct, signal.reason,
                        current.open_time,
                    )
                    if trade:
                        trades.append(trade)
                        pending_buy = trade

                elif signal.action == TradeSide.SELL and has_position:
                    trade = self._execute_sell(
                        wallet, symbol, market_price,
                        signal.quantity_pct, signal.reason,
                        current.open_time, pending_buy,
                    )
                    if trade:
                        trades.append(trade)
                        pending_buy = None

            # Record equity
            current_prices = {symbol: current.close}
            eq = float(wallet.equity(current_prices))
            equity_curve.append((current.open_time, eq))
            wallet.update_peak(current_prices)

        # Compute metrics
        metrics = compute_metrics(
            trades, equity_curve, initial_balance,
            periods_per_year=self._periods_per_year(interval),
        )

        return BacktestReport(
            strategy_type=strategy_type,
            symbol=symbol,
            interval=interval,
            initial_balance=initial_balance,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            total_candles=len(candles),
            trades=trades,
            equity_curve=equity_curve,
            regime_history=regime_history,
            metrics=metrics,
        )

    def _execute_buy(
        self,
        wallet: SimulatedWallet,
        symbol: str,
        market_price: Decimal,
        quantity_pct: Decimal,
        reason: str,
        timestamp: int,
    ) -> SimulatedTrade | None:
        """Execute a simulated BUY."""
        spend_usdt = (wallet.available_usdt * quantity_pct).quantize(
            Decimal("0.00000001")
        )
        if spend_usdt <= Decimal("0"):
            return None

        exec_price, slippage_amt = apply_slippage(
            market_price, spend_usdt, TradeSide.BUY
        )
        fee = calculate_fee(spend_usdt, self.fee_rate)
        net_spend = spend_usdt - fee
        quantity = (net_spend / exec_price).quantize(Decimal("0.00000001"))

        if quantity <= Decimal("0"):
            return None

        wallet.debit(spend_usdt)
        wallet.open_position(symbol, quantity, exec_price, fee, float(timestamp))

        return SimulatedTrade(
            side="BUY",
            symbol=symbol,
            quantity=float(quantity),
            entry_price=float(exec_price),
            entry_time=timestamp,
            fee=float(fee),
            reason=reason,
        )

    def _execute_sell(
        self,
        wallet: SimulatedWallet,
        symbol: str,
        market_price: Decimal,
        quantity_pct: Decimal,
        reason: str,
        timestamp: int,
        pending_buy: SimulatedTrade | None,
    ) -> SimulatedTrade | None:
        """Execute a simulated SELL."""
        position = wallet.get_position(symbol)
        if position is None:
            return None

        sell_qty = (position.quantity * quantity_pct).quantize(Decimal("0.00000001"))
        if sell_qty <= Decimal("0"):
            return None

        notional = sell_qty * market_price
        exec_price, slippage_amt = apply_slippage(
            market_price, notional, TradeSide.SELL
        )

        gross_proceeds = sell_qty * exec_price
        fee = calculate_fee(gross_proceeds, self.fee_rate)
        net_proceeds = gross_proceeds - fee

        cost_basis = sell_qty * position.entry_price
        entry_fee_portion = (
            position.entry_fee * sell_qty / position.quantity
        ).quantize(Decimal("0.00000001"))
        pnl = net_proceeds - cost_basis - entry_fee_portion
        pnl_pct = float(pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        wallet.credit(net_proceeds)

        remaining = position.quantity - sell_qty
        if remaining <= Decimal("0.00000001"):
            wallet.close_position(symbol)
        else:
            position.quantity = remaining
            position.entry_fee -= entry_fee_portion

        entry_price = float(pending_buy.entry_price) if pending_buy else float(position.entry_price)
        entry_time = pending_buy.entry_time if pending_buy else 0

        return SimulatedTrade(
            side="SELL",
            symbol=symbol,
            quantity=float(sell_qty),
            entry_price=entry_price,
            exit_price=float(exec_price),
            entry_time=entry_time,
            exit_time=timestamp,
            pnl=float(pnl),
            pnl_pct=round(pnl_pct, 4),
            fee=float(fee),
            reason=reason,
        )

    @staticmethod
    def _periods_per_year(interval: str) -> int:
        """Convert interval to number of periods per year."""
        mapping = {
            "1m": 525600,
            "5m": 105120,
            "15m": 35040,
            "1h": 8760,
            "4h": 2190,
            "1d": 365,
        }
        return mapping.get(interval, 8760)
