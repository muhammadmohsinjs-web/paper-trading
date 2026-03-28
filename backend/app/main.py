from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any, Awaitable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.config import get_settings
from app.database import dispose_database, init_database
from app.logging_utils import configure_logging
from app.market.binance_rest import backfill
from app.market.binance_ws import BinanceWSClient
from app.scanner.universe_selector import UniverseSelector
from app.strategies.manager import StrategyManager

logger = logging.getLogger(__name__)

_ws_clients: list[BinanceWSClient] = []
_ws_clients_by_symbol: dict[str, list[BinanceWSClient]] = {}
_bootstrap_task: asyncio.Task | None = None


async def _await_shutdown_group(awaitables: list[Awaitable[Any]], *, label: str) -> None:
    if not awaitables:
        return

    results = await asyncio.gather(*awaitables, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
            logger.error(
                "%s failed during shutdown",
                label,
                exc_info=(type(result), result, result.__traceback__),
            )


async def _stop_ws_clients(clients: list[BinanceWSClient]) -> None:
    await _await_shutdown_group([client.stop() for client in clients], label="websocket client stop")


_SHUTDOWN_STEP_TIMEOUT = 8.0  # seconds per shutdown step before forcing ahead


async def _timed_shutdown_step(name: str, awaitable: Awaitable[Any], **details: Any) -> Any:
    start = monotonic()
    try:
        return await asyncio.wait_for(asyncio.shield(asyncio.ensure_future(awaitable)), timeout=_SHUTDOWN_STEP_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("shutdown step timed out step=%s timeout=%.1fs — forcing ahead", name, _SHUTDOWN_STEP_TIMEOUT)
        return None
    except asyncio.CancelledError:
        logger.warning("shutdown step cancelled step=%s", name)
        return None
    finally:
        elapsed_ms = (monotonic() - start) * 1000
        payload = " ".join(f"{key}={value}" for key, value in details.items())
        if payload:
            logger.info("shutdown step complete step=%s elapsed_ms=%.1f %s", name, elapsed_ms, payload)
        else:
            logger.info("shutdown step complete step=%s elapsed_ms=%.1f", name, elapsed_ms)


async def _subscribe_symbol(symbol: str, ws_clients: list[BinanceWSClient]) -> None:
    """Backfill and start WebSocket streams for a single symbol."""
    await backfill(symbol, "1h", 200)
    await backfill(symbol, "5m", 200)
    await backfill(symbol, "4h", 200)
    clients: list[BinanceWSClient] = []
    for interval in ("1h", "5m", "4h"):
        client = BinanceWSClient(symbol, interval)
        await client.start()
        clients.append(client)
    ws_clients.extend(clients)
    _ws_clients_by_symbol[symbol] = clients


async def _bootstrap_runtime(settings, manager: StrategyManager) -> None:
    global _ws_clients

    ws_clients: list[BinanceWSClient] = []

    try:
        # Phase 1: Determine initial universe
        startup_phase = "universe selection"
        if settings.dynamic_universe_enabled:
            selector = UniverseSelector.get_instance()
            universe = await selector.get_active_universe()
            if not universe:
                logger.warning(
                    "dynamic universe bootstrap returned empty, falling back to static universe"
                )
                universe = list(settings.default_scan_universe)
            # Always include the default symbol
            if settings.default_symbol not in universe:
                universe.insert(0, settings.default_symbol)
            logger.info(
                "dynamic universe initialized with %d symbols",
                len(universe),
            )
        else:
            universe = list(dict.fromkeys([settings.default_symbol, *settings.default_scan_universe]))

        # Phase 2: Backfill and subscribe
        startup_phase = "historical candle backfill and websocket bootstrap"
        for symbol in universe:
            await _subscribe_symbol(symbol, ws_clients)
        _ws_clients = ws_clients

        # Phase 3: Start strategies
        startup_phase = "strategy bootstrap"
        count = await manager.start_all_active()
        logger.info("strategy bootstrap complete active_count=%d", count)
    except asyncio.CancelledError:
        logger.info("runtime bootstrap cancelled during %s", startup_phase)
        raise
    except Exception:
        logger.exception("runtime bootstrap failed during %s", startup_phase)
        await manager.stop_all()
        await _stop_ws_clients(ws_clients)
        if _ws_clients is ws_clients:
            _ws_clients = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _bootstrap_task, _ws_clients

    settings = get_settings()
    manager = StrategyManager.get_instance()
    shutdown_started_at = 0.0

    try:
        await init_database()
        logger.info("database ready")
        _bootstrap_task = asyncio.create_task(
            _bootstrap_runtime(settings, manager),
            name="paper-trading-runtime-bootstrap",
        )

        yield
    except Exception:
        logger.exception("application startup failed during database initialization")
        raise
    finally:
        shutdown_started_at = monotonic()
        running_strategies = getattr(manager, "running_strategies", lambda: [])
        active_strategies = list(running_strategies())
        logger.info(
            "shutdown initiated websocket_clients=%d running_strategies=%d",
            len(_ws_clients),
            len(active_strategies),
        )
        if _bootstrap_task is not None:
            _bootstrap_task.cancel()
            try:
                await _timed_shutdown_step("bootstrap_task", _bootstrap_task)
            except asyncio.CancelledError:
                pass
            _bootstrap_task = None
        ws_client_count = len(_ws_clients)
        await _timed_shutdown_step(
            "websocket_clients",
            _stop_ws_clients(_ws_clients),
            count=ws_client_count,
        )
        _ws_clients.clear()
        stopped_strategies = await _timed_shutdown_step(
            "strategies",
            manager.stop_all(),
            count=len(active_strategies),
        )
        await _timed_shutdown_step("database", dispose_database())
        total_elapsed_ms = (monotonic() - shutdown_started_at) * 1000
        logger.info(
            "shutdown complete elapsed_ms=%.1f websocket_clients=%d strategies_stopped=%s",
            total_elapsed_ms,
            ws_client_count,
            stopped_strategies,
        )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, use_color=settings.log_use_colors)

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    # CORS
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "ok"}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
