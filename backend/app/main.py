from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router as api_router
from app.config import get_settings
from app.database import dispose_database, init_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_database()
    try:
        yield
    finally:
        await dispose_database()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {"service": settings.app_name, "status": "ok"}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
