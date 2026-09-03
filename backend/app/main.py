from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import export, features, orthophoto
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Best-effort DB init. If DATABASE_URL isn't set yet, skip to keep the
    # dev server bootable (the .env is provided later).
    if settings.database_url:
        try:
            init_db()
        except Exception:
            pass
    yield


def _create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(orthophoto.router)
    app.include_router(features.router)
    app.include_router(export.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = _create_app()