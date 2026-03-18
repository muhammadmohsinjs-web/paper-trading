from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.config import get_settings
from app.database import dispose_database, init_database
from app.market.binance_rest import backfill
from app.market.binance_ws import BinanceWSClient
from app.strategies.manager import StrategyManager

logger = logging.getLogger(__name__)

_ws_client: BinanceWSClient | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _ws_client

    # Init DB
    await init_database()
    logger.info("Database initialized")

    # Backfill historical candles
    settings = get_settings()
    await backfill(settings.default_symbol, "5m", 200)

    # Start Binance WebSocket
    _ws_client = BinanceWSClient(settings.default_symbol, "5m")
    await _ws_client.start()

    # Start active strategies
    manager = StrategyManager.get_instance()
    count = await manager.start_all_active()
    logger.info("Started %d active strategies", count)

    try:
        yield
    finally:
        # Shutdown
        if _ws_client:
            await _ws_client.stop()
        await StrategyManager.get_instance().stop_all()
        await dispose_database()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

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
