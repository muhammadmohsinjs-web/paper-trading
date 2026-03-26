from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.engine.conflict_resolver import PinnedSymbol, resolve_conflicts
from app.engine.evaluation_logging import build_symbol_evaluation_log
from app.engine.strategy_scorer import (
    StrategyCandidate,
    evaluate_universe_for_strategy,
    get_strategy_profile,
    resolve_strategy_type,
)
from app.engine.tradability import evaluate_symbol_tradability
from app.market.data_store import DataStore
from app.models.daily_pick import DailyPick
from app.models.position import Position
from app.models.strategy import Strategy
from app.models.symbol_ownership import SymbolOwnership
from app.risk.portfolio import PortfolioPosition, PortfolioRiskManager
from app.scanner.scanner import OpportunityScanner
from app.scanner.universe_selector import UniverseSelector

settings = get_settings()
logger = logging.getLogger(__name__)
SINGLE_SYMBOL_MODE = "single_symbol"
MULTI_COIN_MODE = "multi_coin_shared_wallet"
_coordinated_pick_lock = asyncio.Lock()


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
    return await ensure_strategy_picks(
        session,
        strategy,
        interval=interval,
        selection_date=selection_date,
        force_refresh=force_refresh,
        open_position_symbols=open_position_symbols,
        cycle_id=cycle_id,
    )


async def ensure_strategy_picks(
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
    if not settings.coordinated_pick_enabled or not _supports_coordinated_picks(strategy):
        return await _ensure_daily_picks_legacy(
            session,
            strategy,
            interval=interval,
            selection_date=chosen_date,
            force_refresh=force_refresh,
            open_position_symbols=open_position_symbols,
            cycle_id=cycle_id,
        )

    if not force_refresh:
        existing = await get_daily_picks(session, strategy, selection_date=chosen_date)
        if _picks_are_fresh(existing):
            return existing

    await ensure_coordinated_picks_fresh(
        session,
        strategy,
        interval=interval,
        selection_date=chosen_date,
        force_refresh=force_refresh,
        open_position_symbols=open_position_symbols,
        cycle_id=cycle_id,
    )
    refreshed = await get_daily_picks(session, strategy, selection_date=chosen_date)
    if refreshed or settings.coordinated_pick_enabled:
        return refreshed
    return await _ensure_daily_picks_legacy(
        session,
        strategy,
        interval=interval,
        selection_date=chosen_date,
        force_refresh=force_refresh,
        open_position_symbols=open_position_symbols,
        cycle_id=cycle_id,
    )


async def ensure_coordinated_picks_fresh(
    session: AsyncSession,
    strategy: Strategy,
    *,
    interval: str | None = None,
    selection_date: date | None = None,
    force_refresh: bool = False,
    open_position_symbols: set[str] | None = None,
    cycle_id: str | None = None,
) -> None:
    if not settings.coordinated_pick_enabled or not _supports_coordinated_picks(strategy):
        return

    chosen_date = selection_date or resolve_selection_date(strategy)
    if not force_refresh and not await coordinated_picks_need_refresh(session, selection_date=chosen_date, strategy=strategy):
        return

    async with _coordinated_pick_lock:
        if not force_refresh and not await coordinated_picks_need_refresh(session, selection_date=chosen_date, strategy=strategy):
            return
        strategies = await _get_active_multi_coin_strategies(session, coordinated_only=True)
        if not strategies and _supports_coordinated_picks(strategy):
            strategies = [strategy]
        elif _supports_coordinated_picks(strategy) and strategy.id not in {item.id for item in strategies}:
            strategies.append(strategy)
        if not strategies:
            return
        await ensure_coordinated_picks(
            session,
            strategies,
            interval=interval,
            selection_date=chosen_date,
            cycle_id=cycle_id,
            open_position_symbols=open_position_symbols,
        )


async def coordinated_picks_need_refresh(
    session: AsyncSession,
    *,
    selection_date: date | None = None,
    strategy: Strategy | None = None,
) -> bool:
    chosen_date = selection_date or datetime.now(timezone.utc).date()
    strategies = await _get_active_multi_coin_strategies(session, coordinated_only=True)
    if not strategies and strategy is not None and _supports_coordinated_picks(strategy):
        strategies = [strategy]
    elif strategy is not None and _supports_coordinated_picks(strategy) and strategy.id not in {item.id for item in strategies}:
        strategies.append(strategy)
    if not strategies:
        return False
    for strategy in strategies:
        existing = await get_daily_picks(session, strategy, selection_date=chosen_date)
        if not _picks_are_fresh(existing):
            return True
    return False


async def ensure_coordinated_picks(
    session: AsyncSession,
    strategies: list[Strategy],
    *,
    interval: str | None = None,
    selection_date: date | None = None,
    cycle_id: str | None = None,
    open_position_symbols: set[str] | None = None,
) -> dict[str, list[DailyPick]]:
    if not strategies:
        return {}

    now = datetime.now(timezone.utc)
    chosen_date = selection_date or now.date()
    evaluation_cycle_id = cycle_id or str(uuid4())
    strategies_by_id = {strategy.id: strategy for strategy in strategies}
    strategy_ids = list(strategies_by_id.keys())

    positions = (
        await session.execute(
            select(Position).where(Position.strategy_id.in_(strategy_ids))
        )
    ).scalars().all()
    all_open_symbols = {position.symbol for position in positions} | set(open_position_symbols or set())

    ownership_rows = (
        await session.execute(
            select(SymbolOwnership).where(SymbolOwnership.strategy_id.in_(strategy_ids))
        )
    ).scalars().all()
    active_ownership_by_symbol = {
        row.symbol: row
        for row in ownership_rows
        if row.released_at is None
    }
    cooldowns = {
        (row.strategy_id, row.symbol): cooldown_until
        for row in ownership_rows
        if (cooldown_until := _as_aware(row.cooldown_until)) is not None and cooldown_until > now
    }

    universe_symbols: set[str] = set()
    dynamic_snapshot = None
    if any(not has_explicit_scan_universe(strategy) for strategy in strategies):
        dynamic_scanner = OpportunityScanner()
        if settings.dynamic_universe_enabled:
            dynamic_symbols = await dynamic_scanner.resolve_symbols(retained_symbols=all_open_symbols)
            universe_symbols.update(dynamic_symbols)
            dynamic_snapshot = UniverseSelector.get_instance().get_last_snapshot()
        else:
            universe_symbols.update(dynamic_scanner.symbols)

    for strategy in strategies:
        if has_explicit_scan_universe(strategy):
            universe_symbols.update(resolve_scan_universe(strategy))
        await _log_universe_tradability(
            session,
            strategy,
            interval=interval,
            selection_date=chosen_date,
            cycle_id=evaluation_cycle_id,
            dynamic_snapshot=dynamic_snapshot if not has_explicit_scan_universe(strategy) else None,
        )

    scanner = OpportunityScanner(symbols=sorted(universe_symbols) or list(settings.default_scan_universe))
    scanner_results = scanner.scan_all_setups_for_universe(
        interval=interval or settings.default_candle_interval,
    )
    scanner_audits = scanner.get_last_rank_audit()
    regime_cache = scanner.get_last_regime_cache()

    scored_candidates: dict[str, list[StrategyCandidate]] = {}
    scoring_rejections = []
    per_strategy_max: dict[str, int] = {}

    for strategy in strategies:
        profile = get_strategy_profile(resolve_strategy_type(strategy))
        if profile is None:
            continue
        for audit in scanner_audits:
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
                        "source": "scanner_shared",
                    },
                )
            )

        effective_max = min(resolve_top_pick_count(strategy), profile.max_pick_count)
        per_strategy_max[strategy.id] = effective_max
        scoring_result = evaluate_universe_for_strategy(
            strategy,
            profile,
            scanner_results,
            regime_cache,
            max_pick_count=effective_max,
        )
        scored_candidates[strategy.id] = scoring_result.candidates
        scoring_rejections.extend(scoring_result.rejections)

    pinned_symbols: dict[str, PinnedSymbol] = {}
    for position in positions:
        strategy = strategies_by_id.get(position.strategy_id)
        if strategy is None:
            continue
        strategy_type = resolve_strategy_type(strategy)
        ownership = active_ownership_by_symbol.get(position.symbol)
        pinned_symbols[position.symbol] = PinnedSymbol(
            strategy_id=position.strategy_id,
            strategy_name=strategy.name,
            strategy_type=strategy_type,
            symbol=position.symbol,
            assignment_reason="Pinned open position",
            final_score=float(ownership.assignment_score) if ownership and ownership.assignment_score is not None else 1.0,
            regime="pinned",
            setup_type="open_position",
            recommended_strategy=strategy_type,
            setup_fit_score=1.0,
            regime_fit_score=1.0,
            liquidity_score=1.0,
            perf_memory_score=0.5,
            vol_quality_score=0.5,
            expected_rr_score=0.5,
            liquidity_usdt=0.0,
            market_quality_score=0.0,
            reward_to_cost_ratio=0.0,
        )

    assignments, conflict_rejections = resolve_conflicts(
        scored_candidates,
        pinned_symbols,
        cooldowns,
        per_strategy_max,
        settings.global_max_active_symbols,
        now=now,
    )

    await session.execute(
        delete(DailyPick).where(
            DailyPick.strategy_id.in_(strategy_ids),
            DailyPick.selection_date == chosen_date,
        )
    )

    claim_counts = Counter(
        candidate.symbol
        for candidates in scored_candidates.values()
        for candidate in candidates
    )
    created_by_strategy: dict[str, list[DailyPick]] = {strategy_id: [] for strategy_id in strategy_ids}

    for rejection in scoring_rejections:
        session.add(
            build_symbol_evaluation_log(
                strategy_id=rejection.strategy_id,
                cycle_id=evaluation_cycle_id,
                symbol=rejection.symbol,
                stage="strategy_scoring",
                status="rejected",
                reason_code=rejection.reason_code,
                reason_text=rejection.reason_text,
                metrics_json={},
                context_json={
                    "selection_date": chosen_date.isoformat(),
                    "setup_type": rejection.setup_type,
                    "regime": rejection.regime,
                },
            )
        )

    for rejection in conflict_rejections:
        session.add(
            build_symbol_evaluation_log(
                strategy_id=rejection.strategy_id,
                cycle_id=evaluation_cycle_id,
                symbol=rejection.symbol,
                stage="conflict_resolution",
                status="rejected",
                reason_code=rejection.reason_code,
                reason_text=rejection.reason_text,
                metrics_json={},
                context_json={
                    "selection_date": chosen_date.isoformat(),
                    "setup_type": rejection.setup_type,
                    "regime": rejection.regime,
                },
            )
        )

    for strategy_id, candidates in assignments.items():
        for idx, candidate in enumerate(candidates, start=1):
            conflict_resolution = _resolve_conflict_resolution(candidate, claim_counts)
            item = DailyPick(
                strategy_id=strategy_id,
                selection_date=chosen_date,
                selected_at=now,
                rank=idx,
                symbol=candidate.symbol,
                score=float(candidate.final_score),
                regime=candidate.regime,
                setup_type=candidate.setup_type,
                recommended_strategy=candidate.recommended_strategy,
                reason=candidate.assignment_reason,
                assignment_reason=candidate.assignment_reason,
                conflict_resolution=conflict_resolution,
                setup_fit_score=float(candidate.setup_fit_score),
                regime_fit_score=float(candidate.regime_fit_score),
            )
            session.add(item)
            created_by_strategy.setdefault(strategy_id, []).append(item)
            session.add(
                build_symbol_evaluation_log(
                    strategy_id=strategy_id,
                    cycle_id=evaluation_cycle_id,
                    symbol=candidate.symbol,
                    stage="conflict_resolution",
                    status="assigned",
                    reason_text=candidate.assignment_reason,
                    metrics_json={
                        "final_score": candidate.final_score,
                        "setup_fit_score": candidate.setup_fit_score,
                        "regime_fit_score": candidate.regime_fit_score,
                    },
                    context_json={
                        "selection_date": chosen_date.isoformat(),
                        "conflict_resolution": conflict_resolution,
                        "setup_type": candidate.setup_type,
                        "regime": candidate.regime,
                    },
                )
            )

    await _sync_symbol_ownerships(
        session,
        strategies_by_id,
        active_ownership_by_symbol,
        assignments,
        now,
    )
    await session.flush()
    return created_by_strategy


async def _ensure_daily_picks_legacy(
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
            selected_at = existing[0].selected_at
            if selected_at.tzinfo is None:
                selected_at = selected_at.replace(tzinfo=timezone.utc)
            age_hours = (now - selected_at).total_seconds() / 3600
            if age_hours < PICK_REFRESH_HOURS:
                return existing
            # Picks are stale — re-scan for fresh opportunities
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

    await _log_universe_tradability(
        session,
        strategy,
        interval=interval,
        selection_date=chosen_date,
        cycle_id=evaluation_cycle_id,
        dynamic_snapshot=UniverseSelector.get_instance().get_last_snapshot() if not explicit_universe else None,
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


def _supports_coordinated_picks(strategy: Strategy) -> bool:
    return get_strategy_profile(resolve_strategy_type(strategy)) is not None


def _picks_are_fresh(picks: list[DailyPick], *, now: datetime | None = None) -> bool:
    if not picks:
        return False
    current = now or datetime.now(timezone.utc)
    selected_at = _as_aware(picks[0].selected_at)
    if selected_at is None:
        return False
    age_hours = (current - selected_at).total_seconds() / 3600
    return age_hours < PICK_REFRESH_HOURS


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _get_active_multi_coin_strategies(
    session: AsyncSession,
    *,
    coordinated_only: bool,
) -> list[Strategy]:
    strategies = (
        await session.execute(
            select(Strategy).where(
                Strategy.is_active.is_(True),
                Strategy.execution_mode == MULTI_COIN_MODE,
            )
        )
    ).scalars().all()
    if coordinated_only:
        return [strategy for strategy in strategies if _supports_coordinated_picks(strategy)]
    return list(strategies)


async def _log_universe_tradability(
    session: AsyncSession,
    strategy: Strategy,
    *,
    interval: str | None,
    selection_date: date,
    cycle_id: str,
    dynamic_snapshot: Any | None,
) -> None:
    if dynamic_snapshot is not None:
        for candidate in dynamic_snapshot.candidate_evaluations:
            session.add(
                build_symbol_evaluation_log(
                    strategy_id=strategy.id,
                    cycle_id=cycle_id,
                    symbol=candidate.symbol,
                    stage="universe_tradability",
                    status="passed" if candidate.tradability_passed else "rejected",
                    reason_code=(candidate.reason_codes[0] if candidate.reason_codes else None),
                    reason_text=candidate.reason_text,
                    metrics_json=candidate.metrics,
                    context_json={
                        "selection_date": selection_date.isoformat(),
                        "market_quality_score": candidate.market_quality_score,
                        "source": "dynamic",
                    },
                )
            )
        return

    scanner_symbols = resolve_scan_universe(strategy)
    store = DataStore.get_instance()
    for symbol in scanner_symbols:
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
                cycle_id=cycle_id,
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
                context_json={"selection_date": selection_date.isoformat(), "source": "explicit"},
            )
        )


def _resolve_conflict_resolution(candidate: StrategyCandidate, claim_counts: Counter[str]) -> str:
    if candidate.setup_type == "open_position":
        return "primary_match"
    if claim_counts.get(candidate.symbol, 0) <= 1:
        return "no_conflict"
    if candidate.recommended_strategy == candidate.strategy_type:
        return "primary_match"
    return "won_conflict"


async def _sync_symbol_ownerships(
    session: AsyncSession,
    strategies_by_id: dict[str, Strategy],
    active_ownership_by_symbol: dict[str, SymbolOwnership],
    assignments: dict[str, list[StrategyCandidate]],
    now: datetime,
) -> None:
    cooldown_delta = timedelta(hours=settings.symbol_ownership_cooldown_hours)
    assigned_by_symbol = {
        candidate.symbol: candidate
        for candidates in assignments.values()
        for candidate in candidates
    }

    for symbol, ownership in active_ownership_by_symbol.items():
        if symbol in assigned_by_symbol:
            continue
        ownership.released_at = now
        ownership.release_reason = ownership.release_reason or "refresh_unassigned"
        ownership.cooldown_until = now + cooldown_delta

    for symbol, candidate in assigned_by_symbol.items():
        existing = active_ownership_by_symbol.get(symbol)
        if existing is not None and existing.strategy_id == candidate.strategy_id and existing.released_at is None:
            existing.strategy_name = strategies_by_id[candidate.strategy_id].name
            existing.assignment_score = candidate.final_score
            existing.assignment_reason = candidate.assignment_reason
            existing.cooldown_until = None
            continue
        if existing is not None and existing.released_at is None:
            existing.released_at = now
            existing.release_reason = "reassigned"
            existing.cooldown_until = now + cooldown_delta
        session.add(
            SymbolOwnership(
                symbol=symbol,
                strategy_id=candidate.strategy_id,
                strategy_name=strategies_by_id[candidate.strategy_id].name,
                assigned_at=now,
                released_at=None,
                release_reason=None,
                cooldown_until=None,
                assignment_score=candidate.final_score,
                assignment_reason=candidate.assignment_reason,
            )
        )


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
