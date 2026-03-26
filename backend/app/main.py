from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.config import get_settings
from app.database import dispose_database, init_database
from app.logging_utils import configure_logging
from app.market.binance_rest import backfill
from app.market.binance_ws import BinanceWSClient
from app.strategies.manager import StrategyManager

logger = logging.getLogger(__name__)

_ws_clients: list[BinanceWSClient] = []
_bootstrap_task: asyncio.Task | None = None


async def _bootstrap_runtime(settings, manager: StrategyManager) -> None:
    global _ws_clients

    universe = list(dict.fromkeys([settings.default_symbol, *settings.default_scan_universe]))
    startup_phase = "historical candle backfill"
    ws_clients: list[BinanceWSClient] = []

    try:
        for symbol in universe:
            await backfill(symbol, "1h", 200)
            await backfill(symbol, "5m", 200)
            await backfill(symbol, "4h", 200)

        startup_phase = "websocket bootstrap"
        for symbol in universe:
            ws_1h = BinanceWSClient(symbol, "1h")
            ws_5m = BinanceWSClient(symbol, "5m")
            ws_4h = BinanceWSClient(symbol, "4h")
            await ws_1h.start()
            await ws_5m.start()
            await ws_4h.start()
            ws_clients.extend([ws_1h, ws_5m, ws_4h])
        _ws_clients = ws_clients

        startup_phase = "strategy bootstrap"
        count = await manager.start_all_active()
        logger.info("strategy bootstrap complete active_count=%d", count)
    except asyncio.CancelledError:
        logger.info("runtime bootstrap cancelled during %s", startup_phase)
        raise
    except Exception:
        logger.exception("runtime bootstrap failed during %s", startup_phase)
        await manager.stop_all()
        for client in ws_clients:
            await client.stop()
        if _ws_clients is ws_clients:
            _ws_clients = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _bootstrap_task, _ws_clients

    settings = get_settings()
    manager = StrategyManager.get_instance()

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
        if _bootstrap_task is not None:
            _bootstrap_task.cancel()
            try:
                await _bootstrap_task
            except asyncio.CancelledError:
                pass
            _bootstrap_task = None
        for client in _ws_clients:
            await client.stop()
        _ws_clients.clear()
        await manager.stop_all()
        await dispose_database()
        logger.info("shutdown complete")


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
