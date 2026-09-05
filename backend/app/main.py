from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import export, features, orthophoto, report
from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    import logging
    log = logging.getLogger("vectoreye.startup")

    # Log ML / GPU status
    log.info("ML_ENABLED=%s  ML_DEVICE=%s", settings.ml_enabled, settings.ml_device)
    try:
        import torch
        log.info("PyTorch %s  CUDA available: %s", torch.__version__, torch.cuda.is_available())
        if torch.cuda.is_available():
            log.info("GPU: %s  VRAM: %.0f MB", torch.cuda.get_device_name(0), torch.cuda.get_device_properties(0).total_memory / 1e6)
    except ImportError:
        log.warning("PyTorch is not installed — ML inference will not work")

    # Log storage paths
    from .services.storage import UPLOAD_ROOT
    log.info("UPLOAD_ROOT=%s (exists=%s)", UPLOAD_ROOT, UPLOAD_ROOT.exists())

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
    app.include_router(report.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = _create_app()