"""In-memory wallet for backtesting — mirrors the Wallet model interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class SimulatedPosition:
    """In-memory position for backtesting."""

    symbol: str
    quantity: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    entry_fee: Decimal = Decimal("0")
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    trailing_stop_price: Decimal | None = None
    entry_atr: Decimal | None = None
    opened_at: float | None = None  # timestamp


@dataclass
class SimulatedWallet:
    """In-memory wallet for backtesting — no DB writes."""

    initial_balance_usdt: Decimal = Decimal("1000")
    available_usdt: Decimal = Decimal("1000")
    peak_equity_usdt: Decimal = Decimal("1000")
    daily_loss_usdt: Decimal = Decimal("0")
    weekly_loss_usdt: Decimal = Decimal("0")
    daily_loss_reset_date: object = None
    weekly_loss_reset_date: object = None
    positions: dict[str, SimulatedPosition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.available_usdt = self.initial_balance_usdt
        self.peak_equity_usdt = self.initial_balance_usdt

    @property
    def has_position(self) -> bool:
        return bool(self.positions)

    def get_position(self, symbol: str) -> SimulatedPosition | None:
        return self.positions.get(symbol)

    def equity(self, current_prices: dict[str, float]) -> Decimal:
        """Total equity = cash + mark-to-market positions."""
        total = self.available_usdt
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol)
            if price is not None:
                total += pos.quantity * Decimal(str(price))
        return total

    def debit(self, amount: Decimal) -> None:
        if self.available_usdt < amount:
            raise ValueError(
                f"Insufficient balance: have {self.available_usdt}, need {amount}"
            )
        self.available_usdt -= amount

    def credit(self, amount: Decimal) -> None:
        self.available_usdt += amount

    def open_position(
        self,
        symbol: str,
        quantity: Decimal,
        entry_price: Decimal,
        entry_fee: Decimal,
        timestamp: float | None = None,
    ) -> SimulatedPosition:
        existing = self.positions.get(symbol)
        if existing:
            # Average into existing position
            total_qty = existing.quantity + quantity
            existing.entry_price = (
                (existing.entry_price * existing.quantity + entry_price * quantity) / total_qty
            ).quantize(Decimal("0.00000001"))
            existing.quantity = total_qty
            existing.entry_fee += entry_fee
            return existing

        pos = SimulatedPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            entry_fee=entry_fee,
            opened_at=timestamp,
        )
        self.positions[symbol] = pos
        return pos

    def close_position(self, symbol: str) -> SimulatedPosition | None:
        return self.positions.pop(symbol, None)

    def update_peak(self, current_prices: dict[str, float]) -> None:
        eq = self.equity(current_prices)
        if eq > self.peak_equity_usdt:
            self.peak_equity_usdt = eq
