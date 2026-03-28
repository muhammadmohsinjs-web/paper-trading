"""Strategy CRUD endpoints."""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import (
    default_ai_model_for_provider,
    get_settings,
)
from app.database import get_db_session
from app.engine.multi_coin import (
    build_open_exposure_by_symbol,
    build_portfolio_status,
    compute_total_equity,
    compute_unrealized_pnl,
    ensure_daily_picks,
    get_daily_picks,
    resolve_primary_symbol,
)
from app.engine.tradability import is_stablecoin_symbol
from app.engine.wallet_manager import get_wallet
from app.models.ai_call_log import AICallLog
from app.models.daily_pick import DailyPick
from app.models.enums import TradeSide
from app.models.position import Position
from app.models.snapshot import Snapshot
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.wallet import Wallet
from app.market.data_store import DataStore
from app.schemas.wallet import PositionResponse, WalletResponse
from app.schemas.strategy import (
    DailyPickResponse,
    StrategyCreate,
    StrategyResponse,
    StrategyUpdate,
    StrategyWithStats,
)
from app.strategies.manager import StrategyManager, resolve_strategy_interval

router = APIRouter(prefix="/strategies", tags=["strategies"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _normalize_explicit_scan_universe(raw_universe: object) -> list[str]:
    if not isinstance(raw_universe, list):
        return []
    return [
        candidate
        for symbol in raw_universe
        if (candidate := str(symbol).upper().strip())
        and not is_stablecoin_symbol(candidate, quote_asset=settings.default_quote_asset)
    ]


def _strategy_ai_defaults(strategy: Strategy) -> dict[str, object]:
    config = strategy.config_json or {}
    provider = settings.ai_provider
    return {
        "ai_enabled": bool(strategy.ai_enabled or config.get("ai_enabled", False)),
        "ai_provider": provider,
        "ai_strategy_key": strategy.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type"),
        "ai_model": default_ai_model_for_provider(provider, settings),
        "ai_cooldown_seconds": int(strategy.ai_cooldown_seconds or config.get("ai_cooldown_seconds") or 60),
        "ai_max_tokens": int(strategy.ai_max_tokens or config.get("ai_max_tokens") or 700),
        "ai_temperature": float(strategy.ai_temperature),
        "ai_last_decision_at": strategy.ai_last_decision_at,
        "ai_last_decision_status": strategy.ai_last_decision_status,
        "ai_last_reasoning": strategy.ai_last_reasoning,
        "ai_last_provider": strategy.ai_last_provider,
        "ai_last_model": strategy.ai_last_model,
        "ai_last_prompt_tokens": strategy.ai_last_prompt_tokens,
        "ai_last_completion_tokens": strategy.ai_last_completion_tokens,
        "ai_last_total_tokens": strategy.ai_last_total_tokens,
        "ai_last_cost_usdt": float(strategy.ai_last_cost_usdt),
        "ai_total_calls": strategy.ai_total_calls,
        "ai_total_prompt_tokens": strategy.ai_total_prompt_tokens,
        "ai_total_completion_tokens": strategy.ai_total_completion_tokens,
        "ai_total_tokens": strategy.ai_total_tokens,
        "ai_total_cost_usdt": float(strategy.ai_total_cost_usdt),
        "stop_loss_pct": float(strategy.stop_loss_pct),
        "max_drawdown_pct": float(strategy.max_drawdown_pct),
        "risk_per_trade_pct": float(strategy.risk_per_trade_pct),
        "max_position_size_pct": float(strategy.max_position_size_pct),
        "candle_interval": strategy.candle_interval,
        "consecutive_losses": strategy.consecutive_losses,
        "max_consecutive_losses": strategy.max_consecutive_losses,
        "streak_size_multiplier": float(strategy.streak_size_multiplier),
    }


def _resolve_initial_balance(strategy: Strategy) -> Decimal:
    config = strategy.config_json or {}
    return Decimal(str(config.get("initial_balance", settings.default_balance_usdt)))


async def _build_stats(session: AsyncSession, strategy: Strategy) -> StrategyWithStats:
    """Build a StrategyWithStats from DB data."""
    # Wallet
    wallet = await get_wallet(session, strategy.id)

    # Trade stats
    trade_result = await session.execute(
        select(
            func.count(Trade.id),
            func.count(Trade.pnl).filter(Trade.pnl > 0),
            func.coalesce(func.sum(Trade.pnl), 0),
        ).where(Trade.strategy_id == strategy.id, Trade.side == TradeSide.SELL)
    )
    row = trade_result.one()
    sell_count, winning, total_pnl = int(row[0]), int(row[1]), float(row[2])

    total_trade_result = await session.execute(
        select(func.count(Trade.id)).where(Trade.strategy_id == strategy.id)
    )
    total_trades = total_trade_result.scalar() or 0

    position_result = await session.execute(
        select(Position).where(Position.strategy_id == strategy.id).order_by(Position.opened_at.desc())
    )
    positions = list(position_result.scalars().all())
    has_open_position = bool(positions)
    unrealized_pnl = float(compute_unrealized_pnl(positions)) if positions else 0.0
    fallback_balance = float(_resolve_initial_balance(strategy))
    total_equity = float(compute_total_equity(wallet, positions)) if wallet else fallback_balance
    open_exposure_by_symbol = build_open_exposure_by_symbol(positions) if positions else {}
    portfolio_risk_status = build_portfolio_status(strategy, wallet, positions) if wallet else {}
    daily_picks = await get_daily_picks(session, strategy)
    non_stable_positions = [
        position
        for position in positions
        if not is_stablecoin_symbol(position.symbol, quote_asset=settings.default_quote_asset)
    ]
    focus_symbol = (
        non_stable_positions[0].symbol
        if non_stable_positions
        else daily_picks[0].symbol if daily_picks
        else resolve_primary_symbol(strategy)
    )

    return StrategyWithStats(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        config_json=strategy.config_json or {},
        is_active=strategy.is_active,
        execution_mode=strategy.execution_mode,
        primary_symbol=strategy.primary_symbol,
        scan_universe_json=_normalize_explicit_scan_universe(strategy.scan_universe_json or []),
        top_pick_count=strategy.top_pick_count,
        selection_hour_utc=strategy.selection_hour_utc,
        max_concurrent_positions=strategy.max_concurrent_positions,
        **_strategy_ai_defaults(strategy),
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
        available_usdt=float(wallet.available_usdt) if wallet else fallback_balance,
        initial_balance_usdt=float(wallet.initial_balance_usdt) if wallet else fallback_balance,
        total_equity=total_equity,
        total_trades=total_trades,
        winning_trades=winning,
        total_pnl=total_pnl,
        unrealized_pnl=unrealized_pnl,
        has_open_position=has_open_position,
        win_rate=round(winning / sell_count * 100, 2) if sell_count else 0.0,
        focus_symbol=focus_symbol,
        open_positions_count=len(positions),
        open_exposure_by_symbol=open_exposure_by_symbol,
        portfolio_risk_status=portfolio_risk_status,
        daily_picks=[
            DailyPickResponse(
                rank=pick.rank,
                symbol=pick.symbol,
                score=round(float(pick.score), 4),
                regime=pick.regime,
                setup_type=pick.setup_type,
                recommended_strategy=pick.recommended_strategy,
                reason=pick.reason,
                selected_at=pick.selected_at,
            )
            for pick in daily_picks
        ],
        selection_date=daily_picks[0].selection_date.isoformat() if daily_picks else None,
    )


@router.get("", response_model=list[StrategyWithStats])
async def list_strategies(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    strategies = result.scalars().all()
    return [await _build_stats(session, s) for s in strategies]


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(
    body: StrategyCreate,
    session: AsyncSession = Depends(get_db_session),
):
    config_json = body.config_json or {}
    explicit_scan_universe = (
        body.scan_universe_json
        if body.scan_universe_json is not None
        else config_json.get("scan_universe")
    )
    scan_universe = _normalize_explicit_scan_universe(explicit_scan_universe)
    strategy = Strategy(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        config_json=config_json,
        is_active=body.is_active,
        execution_mode=body.execution_mode or config_json.get("execution_mode") or "single_symbol",
        primary_symbol=(body.primary_symbol or config_json.get("primary_symbol") or settings.default_symbol).upper(),
        scan_universe_json=scan_universe,
        top_pick_count=body.top_pick_count or config_json.get("top_pick_count") or settings.multi_coin_top_pick_count,
        selection_hour_utc=body.selection_hour_utc if body.selection_hour_utc is not None else config_json.get("selection_hour_utc", settings.multi_coin_selection_hour_utc),
        max_concurrent_positions=body.max_concurrent_positions or config_json.get("max_concurrent_positions") or settings.multi_coin_max_concurrent_positions,
        ai_enabled=body.ai_enabled or bool(config_json.get("ai_enabled", False)),
        ai_provider=settings.ai_provider,
        ai_strategy_key=body.ai_strategy_key or config_json.get("ai_strategy_key") or config_json.get("strategy_type"),
        ai_model=default_ai_model_for_provider(settings.ai_provider, settings),
        ai_cooldown_seconds=body.ai_cooldown_seconds or config_json.get("ai_cooldown_seconds") or 60,
        ai_max_tokens=body.ai_max_tokens or config_json.get("ai_max_tokens") or 700,
        ai_temperature=Decimal(
            str(
                body.ai_temperature
                if body.ai_temperature is not None
                else config_json.get("ai_temperature", 0.2)
            )
        ),
        stop_loss_pct=Decimal(str(body.stop_loss_pct or settings.default_stop_loss_pct)),
        max_drawdown_pct=Decimal(str(body.max_drawdown_pct or settings.default_max_drawdown_pct)),
        risk_per_trade_pct=Decimal(str(body.risk_per_trade_pct or settings.default_risk_per_trade_pct)),
        max_position_size_pct=Decimal(str(body.max_position_size_pct or settings.default_max_position_size_pct)),
        candle_interval=body.candle_interval or settings.default_candle_interval,
    )
    session.add(strategy)
    await session.flush()

    # Create wallet
    initial = _resolve_initial_balance(strategy)
    wallet = Wallet(
        id=str(uuid4()),
        strategy_id=strategy.id,
        initial_balance_usdt=initial,
        available_usdt=initial,
        peak_equity_usdt=initial,
    )
    session.add(wallet)
    session.add(
        Snapshot(
            strategy_id=strategy.id,
            total_equity_usdt=initial,
        )
    )

    if strategy.execution_mode == "multi_coin_shared_wallet":
        try:
            await ensure_daily_picks(session, strategy, interval=strategy.candle_interval, force_refresh=False)
        except Exception:
            logger.exception("failed to initialize daily picks strategy_id=%s", strategy.id)

    await session.commit()
    await session.refresh(strategy)

    # Auto-start if active
    if strategy.is_active:
        await StrategyManager.get_instance().start_strategy(
            strategy.id,
            resolve_strategy_interval(strategy),
        )

    return strategy


@router.get("/{strategy_id}", response_model=StrategyWithStats)
async def get_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")
    return await _build_stats(session, strategy)


@router.get("/{strategy_id}/wallet", response_model=WalletResponse)
async def get_strategy_wallet(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    wallet = await get_wallet(session, strategy_id)
    if wallet is None:
        raise HTTPException(404, "Wallet not found")
    return wallet


@router.get("/{strategy_id}/positions", response_model=list[PositionResponse])
async def get_strategy_positions(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    strategy_result = await session.execute(
        select(Strategy.id).where(Strategy.id == strategy_id)
    )
    if strategy_result.scalar_one_or_none() is None:
        raise HTTPException(404, "Strategy not found")

    result = await session.execute(
        select(Position).where(Position.strategy_id == strategy_id).order_by(Position.opened_at.desc())
    )
    positions = result.scalars().all()
    store = DataStore.get_instance()

    return [
        PositionResponse(
            id=position.id,
            strategy_id=position.strategy_id,
            symbol=position.symbol,
            side=position.side,
            quantity=float(position.quantity),
            entry_price=float(position.entry_price),
            entry_fee=float(position.entry_fee),
            opened_at=position.opened_at,
            stop_loss_price=float(position.stop_loss_price) if position.stop_loss_price is not None else None,
            take_profit_price=float(position.take_profit_price) if position.take_profit_price is not None else None,
            trailing_stop_price=float(position.trailing_stop_price) if position.trailing_stop_price is not None else None,
            entry_atr=float(position.entry_atr) if position.entry_atr is not None else None,
            entry_confidence_raw=(
                float(position.entry_confidence_raw)
                if position.entry_confidence_raw is not None
                else None
            ),
            entry_confidence_final=(
                float(position.entry_confidence_final)
                if position.entry_confidence_final is not None
                else None
            ),
            entry_confidence_bucket=position.entry_confidence_bucket,
            current_price=store.get_latest_price(position.symbol),
            unrealized_pnl=(
                (float(store.get_latest_price(position.symbol)) - float(position.entry_price))
                * float(position.quantity)
                - float(position.entry_fee)
            )
            if store.get_latest_price(position.symbol) is not None
            else None,
        )
        for position in positions
    ]


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: str,
    body: StrategyUpdate,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(strategy, key, value)

    config = strategy.config_json or {}
    if "ai_enabled" in updates and body.ai_enabled is not None:
        strategy.ai_enabled = body.ai_enabled
    if "ai_strategy_key" in updates:
        strategy.ai_strategy_key = body.ai_strategy_key or config.get("ai_strategy_key") or config.get("strategy_type")
    strategy.ai_provider = settings.ai_provider
    strategy.ai_model = default_ai_model_for_provider(settings.ai_provider, settings)
    if "ai_cooldown_seconds" in updates and body.ai_cooldown_seconds is not None:
        strategy.ai_cooldown_seconds = body.ai_cooldown_seconds
    if "ai_max_tokens" in updates and body.ai_max_tokens is not None:
        strategy.ai_max_tokens = body.ai_max_tokens
    if "ai_temperature" in updates and body.ai_temperature is not None:
        strategy.ai_temperature = Decimal(str(body.ai_temperature))
    if "primary_symbol" in updates and strategy.primary_symbol:
        strategy.primary_symbol = strategy.primary_symbol.upper()
    if "scan_universe_json" in updates:
        strategy.scan_universe_json = _normalize_explicit_scan_universe(strategy.scan_universe_json)

    # Handle start/stop
    manager = StrategyManager.get_instance()
    if "is_active" in updates:
        if body.is_active:
            await manager.start_strategy(strategy.id, resolve_strategy_interval(strategy))
        else:
            await manager.stop_strategy(strategy.id)

    await session.commit()
    await session.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, "Strategy not found")

    await StrategyManager.get_instance().stop_strategy(strategy_id)
    await session.execute(delete(AICallLog).where(AICallLog.strategy_id == strategy_id))
    await session.execute(delete(DailyPick).where(DailyPick.strategy_id == strategy_id))
    await session.execute(delete(Snapshot).where(Snapshot.strategy_id == strategy_id))
    await session.execute(delete(Trade).where(Trade.strategy_id == strategy_id))
    await session.execute(delete(Position).where(Position.strategy_id == strategy_id))
    # Only delete wallet in per-strategy mode; shared wallet is kept
    settings = get_settings()
    if not settings.shared_wallet_enabled:
        await session.execute(delete(Wallet).where(Wallet.strategy_id == strategy_id))
    await session.delete(strategy)
    await session.commit()
