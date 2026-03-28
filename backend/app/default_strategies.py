from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.models.wallet import Wallet

DEFAULT_EXECUTION_MODE = "multi_coin_shared_wallet"
DEFAULT_PRIMARY_SYMBOL = "BTCUSDT"


@dataclass(frozen=True)
class DefaultStrategySpec:
    name: str
    description: str
    config_json: dict[str, Any]
    aliases: tuple[str, ...] = ()
    execution_mode: str = DEFAULT_EXECUTION_MODE
    primary_symbol: str = DEFAULT_PRIMARY_SYMBOL
    scan_universe_json: tuple[str, ...] = ()
    top_pick_count: int = 5
    selection_hour_utc: int = 0
    max_concurrent_positions: int = 2
    ai_enabled: bool = False
    ai_cooldown_seconds: int = 60
    ai_max_tokens: int = 700
    ai_temperature: Decimal = Decimal("0.2")
    stop_loss_pct: Decimal = Decimal("3.0")
    max_drawdown_pct: Decimal = Decimal("15.0")
    risk_per_trade_pct: Decimal = Decimal("2.0")
    max_position_size_pct: Decimal = Decimal("30.0")
    candle_interval: str = "1h"
    is_active: bool = True

    @property
    def strategy_type(self) -> str:
        return str(self.config_json["strategy_type"])

    @property
    def initial_balance(self) -> Decimal:
        return Decimal(str(self.config_json.get("initial_balance", 1000)))

    @property
    def match_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


DEFAULT_STRATEGY_SPECS: tuple[DefaultStrategySpec, ...] = (
    DefaultStrategySpec(
        name="SMA Crossover (10/50)",
        description="Buy when SMA-10 crosses above SMA-50, sell on death cross. Classic trend-following with volume confirmation.",
        config_json={
            "strategy_type": "sma_crossover",
            "sma_short": 10,
            "sma_long": 50,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
        aliases=("SMA Crossover",),
    ),
    DefaultStrategySpec(
        name="RSI Mean Reversion",
        description="Buy when RSI drops below 30 (oversold), sell when RSI rises above 70 (overbought). Catches reversals.",
        config_json={
            "strategy_type": "rsi_mean_reversion",
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    ),
    DefaultStrategySpec(
        name="MACD Momentum",
        description="Buy on MACD bullish crossover (MACD crosses above signal line), sell on bearish crossover. Momentum-based.",
        config_json={
            "strategy_type": "macd_momentum",
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    ),
    DefaultStrategySpec(
        name="Bollinger Bounce",
        description="Buy when price touches lower Bollinger Band, sell at upper band. Mean-reversion on volatility bands.",
        config_json={
            "strategy_type": "bollinger_bounce",
            "bb_period": 20,
            "bb_std_dev": 2.0,
            "initial_balance": 1000,
            "interval_seconds": 300,
        },
    ),
    DefaultStrategySpec(
        name="Hybrid AI Composite",
        description="Combines RSI, MACD, SMA, EMA, Volume + AI advisor. Weighted composite scoring with confidence gates.",
        config_json={
            "strategy_type": "hybrid_composite",
            "initial_balance": 1000,
            "interval_seconds": 300,
            "sma_short": 10,
            "sma_long": 50,
            "confidence_gate": 0.5,
            "ai_enabled": True,
            "ai_cooldown_seconds": 300,
            "ai_max_tokens": 700,
            "ai_temperature": 0.2,
        },
        ai_enabled=True,
    ),
)

def _is_default_strategy(strategy: Strategy) -> bool:
    return any(strategy.name in spec.match_names for spec in DEFAULT_STRATEGY_SPECS)


async def _ensure_wallet_and_snapshot(session: AsyncSession, strategy: Strategy, initial_balance: Decimal) -> None:
    wallet_result = await session.execute(
        select(Wallet).where(Wallet.strategy_id == strategy.id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if wallet is None:
        session.add(
            Wallet(
                id=str(uuid4()),
                strategy_id=strategy.id,
                initial_balance_usdt=initial_balance,
                available_usdt=initial_balance,
                peak_equity_usdt=initial_balance,
            )
        )

    snapshot_result = await session.execute(
        select(Snapshot.id).where(Snapshot.strategy_id == strategy.id).limit(1)
    )
    snapshot_exists = snapshot_result.scalar_one_or_none() is not None
    if not snapshot_exists:
        session.add(
            Snapshot(
                strategy_id=strategy.id,
                total_equity_usdt=initial_balance,
            )
        )


def _apply_spec(strategy: Strategy, spec: DefaultStrategySpec) -> None:
    strategy.name = spec.name
    strategy.description = spec.description
    strategy.config_json = spec.config_json
    strategy.is_active = spec.is_active
    strategy.execution_mode = spec.execution_mode
    strategy.primary_symbol = spec.primary_symbol
    strategy.scan_universe_json = list(spec.scan_universe_json)
    strategy.top_pick_count = spec.top_pick_count
    strategy.selection_hour_utc = spec.selection_hour_utc
    strategy.max_concurrent_positions = spec.max_concurrent_positions
    strategy.ai_enabled = spec.ai_enabled
    strategy.ai_cooldown_seconds = spec.ai_cooldown_seconds
    strategy.ai_max_tokens = spec.ai_max_tokens
    strategy.ai_temperature = spec.ai_temperature
    strategy.stop_loss_pct = spec.stop_loss_pct
    strategy.max_drawdown_pct = spec.max_drawdown_pct
    strategy.risk_per_trade_pct = spec.risk_per_trade_pct
    strategy.max_position_size_pct = spec.max_position_size_pct
    strategy.candle_interval = spec.candle_interval


async def sync_default_strategies(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.asc()))
    existing = list(result.scalars().all())

    by_name: dict[str, list[Strategy]] = {}
    for strategy in existing:
        by_name.setdefault(strategy.name, []).append(strategy)

    created = 0
    updated = 0
    duplicates = 0

    for spec in DEFAULT_STRATEGY_SPECS:
        matches: list[Strategy] = []
        seen_ids: set[str] = set()
        for name in spec.match_names:
            for strategy in by_name.get(name, []):
                if strategy.id in seen_ids:
                    continue
                matches.append(strategy)
                seen_ids.add(strategy.id)
        canonical = matches[0] if matches else None

        if canonical is None:
            canonical = Strategy(id=str(uuid4()), name=spec.name, config_json={})
            session.add(canonical)
            created += 1
        else:
            updated += 1
            duplicates += max(0, len(matches) - 1)

        _apply_spec(canonical, spec)
        await _ensure_wallet_and_snapshot(session, canonical, spec.initial_balance)

    await session.commit()
    return {
        "created": created,
        "updated": updated,
        "duplicates": duplicates,
    }


async def replace_default_strategies(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.asc()))
    existing = list(result.scalars().all())
    removed = 0

    for strategy in existing:
        if _is_default_strategy(strategy):
            await session.delete(strategy)
            removed += 1

    await session.flush()
    report = await sync_default_strategies(session)
    report["removed"] = removed
    return report
