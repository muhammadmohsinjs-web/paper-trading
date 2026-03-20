"""Main API router aggregating all sub-routers."""

from fastapi import APIRouter

from app.api.ai_logs import router as ai_logs_router
from app.api.dashboard import router as dashboard_router
from app.api.engine import router as engine_router
from app.api.market import router as market_router
from app.api.strategies import router as strategies_router
from app.api.trades import router as trades_router
from app.api.ws import router as ws_router

router = APIRouter()


@router.get("/health", tags=["system"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


router.include_router(ai_logs_router)
router.include_router(strategies_router)
router.include_router(trades_router)
router.include_router(dashboard_router)
router.include_router(market_router)
router.include_router(engine_router)
router.include_router(ws_router)
