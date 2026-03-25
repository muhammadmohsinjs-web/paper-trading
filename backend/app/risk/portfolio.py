"""Portfolio-level risk management — exposure limits, correlation, drawdown protection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.regime.types import MarketRegime

logger = logging.getLogger(__name__)

# Default limits
DEFAULT_MAX_PORTFOLIO_EXPOSURE_PCT = 70.0
DEFAULT_MAX_SINGLE_ASSET_PCT = 40.0
DEFAULT_MAX_CONCURRENT_POSITIONS = 5
DEFAULT_PORTFOLIO_DRAWDOWN_HALT_PCT = 20.0

# Hardcoded correlation matrix (BTC-correlated assets)
CORRELATION_MATRIX: dict[tuple[str, str], float] = {
    ("BTCUSDT", "ETHUSDT"): 0.85,
    ("BTCUSDT", "SOLUSDT"): 0.75,
    ("BTCUSDT", "BNBUSDT"): 0.70,
    ("BTCUSDT", "ADAUSDT"): 0.72,
    ("BTCUSDT", "XRPUSDT"): 0.65,
    ("BTCUSDT", "DOGEUSDT"): 0.60,
    ("ETHUSDT", "SOLUSDT"): 0.80,
    ("ETHUSDT", "BNBUSDT"): 0.72,
    ("ETHUSDT", "ADAUSDT"): 0.70,
}


def get_correlation(symbol_a: str, symbol_b: str) -> float:
    """Get correlation between two symbols. Returns 0.5 if unknown."""
    if symbol_a == symbol_b:
        return 1.0
    key = (symbol_a, symbol_b)
    rev_key = (symbol_b, symbol_a)
    return CORRELATION_MATRIX.get(key, CORRELATION_MATRIX.get(rev_key, 0.5))


@dataclass
class RiskDecision:
    """Result of a portfolio-level risk check."""

    approved: bool
    reason: str
    adjusted_quantity_pct: Decimal | None = None  # if size should be reduced
    warnings: list[str] = field(default_factory=list)


@dataclass
class PortfolioPosition:
    """Lightweight position summary for risk calculations."""

    strategy_id: str
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    current_value: Decimal  # quantity * market_price


class PortfolioRiskManager:
    """Portfolio-wide risk management — operates across all strategies."""

    def __init__(
        self,
        max_exposure_pct: float = DEFAULT_MAX_PORTFOLIO_EXPOSURE_PCT,
        max_single_asset_pct: float = DEFAULT_MAX_SINGLE_ASSET_PCT,
        max_concurrent_positions: int = DEFAULT_MAX_CONCURRENT_POSITIONS,
        portfolio_drawdown_halt_pct: float = DEFAULT_PORTFOLIO_DRAWDOWN_HALT_PCT,
    ):
        self.max_exposure_pct = max_exposure_pct
        self.max_single_asset_pct = max_single_asset_pct
        self.max_concurrent_positions = max_concurrent_positions
        self.portfolio_drawdown_halt_pct = portfolio_drawdown_halt_pct

    def evaluate(
        self,
        proposed_symbol: str,
        proposed_value: Decimal,
        proposed_quantity_pct: Decimal,
        total_portfolio_equity: Decimal,
        portfolio_peak_equity: Decimal,
        open_positions: list[PortfolioPosition],
        regime: MarketRegime | None = None,
    ) -> RiskDecision:
        """Evaluate whether a proposed trade should be allowed.

        Checks all portfolio-level risk constraints.
        """
        warnings: list[str] = []

        # 1. Portfolio drawdown circuit breaker
        if total_portfolio_equity > 0 and portfolio_peak_equity > 0:
            drawdown_pct = float(
                (portfolio_peak_equity - total_portfolio_equity)
                / portfolio_peak_equity * 100
            )
            if drawdown_pct >= self.portfolio_drawdown_halt_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Portfolio drawdown {drawdown_pct:.1f}% exceeds limit "
                        f"{self.portfolio_drawdown_halt_pct}%. All new entries halted."
                    ),
                )

        # 2. CRASH regime — no new entries
        if regime == MarketRegime.CRASH:
            return RiskDecision(
                approved=False,
                reason="CRASH regime detected — no new entries allowed.",
            )

        # 3. Maximum concurrent positions
        if len(open_positions) >= self.max_concurrent_positions:
            return RiskDecision(
                approved=False,
                reason=(
                    f"Max concurrent positions reached ({len(open_positions)}"
                    f"/{self.max_concurrent_positions})."
                ),
            )

        # 4. Total portfolio exposure
        total_position_value = sum(p.current_value for p in open_positions)
        proposed_total = total_position_value + proposed_value
        if total_portfolio_equity > 0:
            exposure_pct = float(proposed_total / total_portfolio_equity * 100)
            if exposure_pct > self.max_exposure_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Portfolio exposure would be {exposure_pct:.1f}%, "
                        f"exceeds limit {self.max_exposure_pct}%."
                    ),
                )

        # 5. Single-asset concentration
        asset_exposure = proposed_value
        for p in open_positions:
            if p.symbol == proposed_symbol:
                asset_exposure += p.current_value

        if total_portfolio_equity > 0:
            asset_pct = float(asset_exposure / total_portfolio_equity * 100)
            if asset_pct > self.max_single_asset_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Single-asset exposure for {proposed_symbol} would be "
                        f"{asset_pct:.1f}%, exceeds limit {self.max_single_asset_pct}%."
                    ),
                )

        # 6. Correlation-aware sizing
        adjusted_pct = proposed_quantity_pct
        for p in open_positions:
            if p.symbol != proposed_symbol:
                corr = get_correlation(proposed_symbol, p.symbol)
                if corr > 0.7:
                    reduction = Decimal(str(1.0 - corr))  # e.g., 0.85 corr -> reduce to 15%
                    adjusted_pct = min(adjusted_pct, adjusted_pct * reduction)
                    warnings.append(
                        f"Position reduced due to {corr:.0%} correlation with {p.symbol}"
                    )

        # 7. HIGH_VOLATILITY regime — reduce position size by 50%
        if regime == MarketRegime.HIGH_VOLATILITY:
            adjusted_pct = adjusted_pct * Decimal("0.5")
            warnings.append("Position size halved due to high volatility regime")

        if adjusted_pct != proposed_quantity_pct:
            return RiskDecision(
                approved=True,
                reason="Approved with size adjustment",
                adjusted_quantity_pct=adjusted_pct,
                warnings=warnings,
            )

        return RiskDecision(
            approved=True,
            reason="All portfolio risk checks passed",
            warnings=warnings,
        )

    def get_portfolio_status(
        self,
        total_portfolio_equity: Decimal,
        portfolio_peak_equity: Decimal,
        open_positions: list[PortfolioPosition],
    ) -> dict[str, Any]:
        """Get current portfolio risk status."""
        total_position_value = sum(p.current_value for p in open_positions)
        exposure_pct = (
            float(total_position_value / total_portfolio_equity * 100)
            if total_portfolio_equity > 0
            else 0.0
        )
        drawdown_pct = (
            float((portfolio_peak_equity - total_portfolio_equity) / portfolio_peak_equity * 100)
            if portfolio_peak_equity > 0
            else 0.0
        )

        # Per-asset breakdown
        asset_exposure: dict[str, float] = {}
        for p in open_positions:
            asset_exposure[p.symbol] = asset_exposure.get(p.symbol, 0.0) + float(p.current_value)

        return {
            "total_equity": float(total_portfolio_equity),
            "peak_equity": float(portfolio_peak_equity),
            "total_position_value": float(total_position_value),
            "exposure_pct": round(exposure_pct, 2),
            "drawdown_pct": round(max(drawdown_pct, 0), 2),
            "open_positions_count": len(open_positions),
            "max_concurrent_positions": self.max_concurrent_positions,
            "asset_exposure": {
                symbol: round(val / float(total_portfolio_equity) * 100, 2)
                if total_portfolio_equity > 0
                else 0.0
                for symbol, val in asset_exposure.items()
            },
            "limits": {
                "max_exposure_pct": self.max_exposure_pct,
                "max_single_asset_pct": self.max_single_asset_pct,
                "max_concurrent_positions": self.max_concurrent_positions,
                "portfolio_drawdown_halt_pct": self.portfolio_drawdown_halt_pct,
            },
        }
