from __future__ import annotations

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _ws_clients

    # Init DB
    await init_database()
    logger.info("database ready")

    # Backfill historical candles for both intervals
    settings = get_settings()
    await backfill(settings.default_symbol, "1h", 200)
    await backfill(settings.default_symbol, "5m", 200)

    # Start Binance WebSocket for both intervals
    ws_1h = BinanceWSClient(settings.default_symbol, "1h")
    ws_5m = BinanceWSClient(settings.default_symbol, "5m")
    await ws_1h.start()
    await ws_5m.start()
    _ws_clients = [ws_1h, ws_5m]

    # Start active strategies
    manager = StrategyManager.get_instance()
    count = await manager.start_all_active()
    logger.info("strategy bootstrap complete active_count=%d", count)

    try:
        yield
    finally:
        # Shutdown
        for client in _ws_clients:
            await client.stop()
        _ws_clients.clear()
        await StrategyManager.get_instance().stop_all()
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
