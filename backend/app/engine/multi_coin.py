from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.evaluation_logging import build_symbol_evaluation_log
from app.engine.tradability import evaluate_symbol_tradability
from app.market.data_store import DataStore
from app.models.daily_pick import DailyPick
from app.models.position import Position
from app.models.strategy import Strategy
from app.risk.portfolio import PortfolioPosition, PortfolioRiskManager
from app.scanner.scanner import OpportunityScanner
from app.scanner.universe_selector import UniverseSelector

settings = get_settings()
SINGLE_SYMBOL_MODE = "single_symbol"
MULTI_COIN_MODE = "multi_coin_shared_wallet"


def resolve_execution_mode(strategy: Strategy) -> str:
    config = strategy.config_json or {}
    return str(
        strategy.execution_mode
        or config.get("execution_mode")
        or SINGLE_SYMBOL_MODE
    )


def resolve_primary_symbol(strategy: Strategy) -> str:
    config = strategy.config_json or {}
    return str(
        strategy.primary_symbol
        or config.get("primary_symbol")
        or config.get("symbol")
        or settings.default_symbol
    ).upper()


def resolve_scan_universe(strategy: Strategy) -> list[str]:
    config = strategy.config_json or {}
    raw_universe = strategy.scan_universe_json or config.get("scan_universe") or settings.default_scan_universe
    normalized = [str(symbol).upper() for symbol in raw_universe if str(symbol).strip()]
    return normalized or settings.default_scan_universe


def has_explicit_scan_universe(strategy: Strategy) -> bool:
    config = strategy.config_json or {}
    return bool(strategy.scan_universe_json or config.get("scan_universe"))


def resolve_top_pick_count(strategy: Strategy) -> int:
    config = strategy.config_json or {}
    return max(1, int(strategy.top_pick_count or config.get("top_pick_count") or settings.multi_coin_top_pick_count))


def resolve_selection_hour(strategy: Strategy) -> int:
    config = strategy.config_json or {}
    value = int(strategy.selection_hour_utc or config.get("selection_hour_utc") or settings.multi_coin_selection_hour_utc)
    return max(0, min(value, 23))


def resolve_max_concurrent_positions(strategy: Strategy) -> int:
    config = strategy.config_json or {}
    return max(
        1,
        int(
            strategy.max_concurrent_positions
            or config.get("max_concurrent_positions")
            or settings.multi_coin_max_concurrent_positions
        ),
    )


def resolve_selection_date(strategy: Strategy, now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    return current.date()


async def get_daily_picks(
    session: AsyncSession,
    strategy: Strategy,
    *,
    selection_date: date | None = None,
) -> list[DailyPick]:
    chosen_date = selection_date or resolve_selection_date(strategy)
    result = await session.execute(
        select(DailyPick)
        .where(
            DailyPick.strategy_id == strategy.id,
            DailyPick.selection_date == chosen_date,
        )
        .order_by(DailyPick.rank.asc())
    )
    return list(result.scalars().all())


PICK_REFRESH_HOURS = settings.dynamic_universe_refresh_hours if settings.dynamic_universe_enabled else 4


async def ensure_daily_picks(
    session: AsyncSession,
    strategy: Strategy,
    *,
    interval: str | None = None,
    selection_date: date | None = None,
    force_refresh: bool = False,
    open_position_symbols: set[str] | None = None,
    cycle_id: str | None = None,
) -> list[DailyPick]:
    chosen_date = selection_date or resolve_selection_date(strategy)
    now = datetime.now(timezone.utc)
    evaluation_cycle_id = cycle_id or str(uuid4())

    if not force_refresh:
        existing = await get_daily_picks(session, strategy, selection_date=chosen_date)
        if existing:
            # Check if picks are stale (older than PICK_REFRESH_HOURS)
            age_hours = (now - existing[0].selected_at).total_seconds() / 3600
            if age_hours < PICK_REFRESH_HOURS:
                return existing
            # Picks are stale — re-scan for fresh opportunities
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                "daily picks are %.1fh old (threshold=%.1fh), refreshing for strategy=%s",
                age_hours, PICK_REFRESH_HOURS, strategy.id,
            )

    explicit_universe = has_explicit_scan_universe(strategy)
    scanner = (
        OpportunityScanner(symbols=resolve_scan_universe(strategy))
        if explicit_universe
        else OpportunityScanner()
    )

    # If dynamic universe is enabled and no explicit universe was set on the strategy,
    # resolve symbols dynamically with position-aware retention.
    if settings.dynamic_universe_enabled and not explicit_universe:
        retained = open_position_symbols or set()
        await scanner.resolve_symbols(retained_symbols=retained)
        snapshot = UniverseSelector.get_instance().get_last_snapshot()
        if snapshot is not None:
            for candidate in snapshot.candidate_evaluations:
                session.add(
                    build_symbol_evaluation_log(
                        strategy_id=strategy.id,
                        cycle_id=evaluation_cycle_id,
                        symbol=candidate.symbol,
                        stage="universe_tradability",
                        status="passed" if candidate.tradability_passed else "rejected",
                        reason_code=(candidate.reason_codes[0] if candidate.reason_codes else None),
                        reason_text=candidate.reason_text,
                        metrics_json=candidate.metrics,
                        context_json={
                            "selection_date": chosen_date.isoformat(),
                            "market_quality_score": candidate.market_quality_score,
                            "source": "dynamic",
                        },
                    )
                )
    elif explicit_universe:
        store = DataStore.get_instance()
        for symbol in scanner.symbols:
            candles = store.get_candles(
                symbol,
                interval or strategy.candle_interval or settings.default_candle_interval,
                200,
            )
            closes = [candle.close for candle in candles]
            highs = [candle.high for candle in candles]
            lows = [candle.low for candle in candles]
            volumes = [candle.volume for candle in candles]
            volume_24h_usdt = sum(close * volume for close, volume in zip(closes[-24:], volumes[-24:]))
            tradability = evaluate_symbol_tradability(
                symbol=symbol,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                volume_24h_usdt=volume_24h_usdt,
                config=strategy.config_json or {},
            ) if candles else None
            session.add(
                build_symbol_evaluation_log(
                    strategy_id=strategy.id,
                    cycle_id=evaluation_cycle_id,
                    symbol=symbol,
                    stage="universe_tradability",
                    status="passed" if tradability is None or tradability.passed else "rejected",
                    reason_code=(tradability.reason_codes[0] if tradability and tradability.reason_codes else "EXPLICIT_UNIVERSE_SYMBOL"),
                    reason_text=(
                        tradability.reason_text
                        if tradability is not None
                        else "Symbol provided by explicit scan universe but missing local candles"
                    ),
                    metrics_json=tradability.metrics.to_dict() if tradability is not None else {},
                    context_json={"selection_date": chosen_date.isoformat(), "source": "explicit"},
                )
            )

    ranked_symbols = scanner.rank_symbols(
        interval=interval or strategy.candle_interval or settings.default_candle_interval,
        max_results=resolve_top_pick_count(strategy),
    )
    for audit in scanner.get_last_rank_audit():
        session.add(
            build_symbol_evaluation_log(
                strategy_id=strategy.id,
                cycle_id=evaluation_cycle_id,
                symbol=str(audit.get("symbol") or ""),
                stage="scanner",
                status=str(audit.get("status") or "rejected"),
                reason_code=audit.get("reason_code"),
                reason_text=audit.get("reason_text"),
                metrics_json={
                    "score": audit.get("score"),
                    "movement_quality": audit.get("movement_quality") or {},
                },
                context_json={
                    "setup_type": audit.get("setup_type"),
                    "selection_date": chosen_date.isoformat(),
                    "source": "scanner_rank",
                },
            )
        )

    await session.execute(
        delete(DailyPick).where(
            DailyPick.strategy_id == strategy.id,
            DailyPick.selection_date == chosen_date,
        )
    )

    created: list[DailyPick] = []
    for idx, candidate in enumerate(ranked_symbols, start=1):
        item = DailyPick(
            strategy_id=strategy.id,
            selection_date=chosen_date,
            selected_at=now,
            rank=idx,
            symbol=candidate.symbol,
            score=float(candidate.score),
            regime=candidate.regime,
            setup_type=candidate.setup_type,
            recommended_strategy=candidate.recommended_strategy,
            reason=candidate.reason,
        )
        session.add(item)
        created.append(item)

    await session.flush()
    return created


def build_portfolio_positions(
    positions: list[Position],
    *,
    strategy_id: str,
) -> list[PortfolioPosition]:
    store = DataStore.get_instance()
    portfolio_positions: list[PortfolioPosition] = []
    for position in positions:
        price = store.get_latest_price(position.symbol)
        if price is None:
            continue
        current_value = position.quantity * Decimal(str(price))
        portfolio_positions.append(
            PortfolioPosition(
                strategy_id=strategy_id,
                symbol=position.symbol,
                quantity=position.quantity,
                entry_price=position.entry_price,
                current_value=current_value,
            )
        )
    return portfolio_positions


def compute_total_equity(wallet: Any, positions: list[Position]) -> Decimal:
    store = DataStore.get_instance()
    total = Decimal(str(wallet.available_usdt))
    for position in positions:
        price = store.get_latest_price(position.symbol)
        if price is None:
            continue
        total += position.quantity * Decimal(str(price))
    return total


def compute_unrealized_pnl(positions: list[Position]) -> Decimal:
    store = DataStore.get_instance()
    total = Decimal("0")
    for position in positions:
        price = store.get_latest_price(position.symbol)
        if price is None:
            continue
        total += (Decimal(str(price)) - position.entry_price) * position.quantity - position.entry_fee
    return total


def build_open_exposure_by_symbol(positions: list[Position]) -> dict[str, float]:
    store = DataStore.get_instance()
    exposures: dict[str, Decimal] = {}
    for position in positions:
        price = store.get_latest_price(position.symbol)
        if price is None:
            continue
        exposures[position.symbol] = exposures.get(position.symbol, Decimal("0")) + (
            position.quantity * Decimal(str(price))
        )
    return {symbol: round(float(value), 2) for symbol, value in exposures.items()}


def build_portfolio_status(strategy: Strategy, wallet: Any, positions: list[Position]) -> dict[str, Any]:
    manager = PortfolioRiskManager(max_concurrent_positions=resolve_max_concurrent_positions(strategy))
    total_equity = compute_total_equity(wallet, positions)
    peak_equity = Decimal(str(wallet.peak_equity_usdt or total_equity))
    portfolio_positions = build_portfolio_positions(positions, strategy_id=strategy.id)
    return manager.get_portfolio_status(total_equity, peak_equity, portfolio_positions)
