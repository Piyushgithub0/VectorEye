from __future__ import annotations

import os
from pathlib import Path

import dotenv

# Load .env from the backend directory (or the repo root).
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
dotenv.load_dotenv(_BACKEND_DIR / ".env")
dotenv.load_dotenv(_REPO_ROOT / ".env")


def _env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings loaded from environment variables."""

    def __init__(self) -> None:
        self.repo_root = _REPO_ROOT
        self.backend_dir = _BACKEND_DIR
        self.app_name = "VectorEye"
        self.version = "0.1.0"

        # Database
        self.database_url = _env_str("DATABASE_URL")
        self.database_driver = _env_str("DATABASE_DRIVER", "psycopg2")

        # CORS
        raw_origins = _env_str("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        self.cors_origins = [o for o in (_o.strip() for _o in raw_origins.split(",")) if o]

        # Paths
        self.upload_dir = Path(_env_str("UPLOAD_DIR", "uploads"))
        self.storage_dir = Path(_env_str("STORAGE_DIR", "storage"))

        # ML
        self.ml_enabled = _env_bool("ML_ENABLED", False)
        self.ml_device = _env_str("ML_DEVICE", "auto")
        self.ml_batch_size = _env_int("ML_BATCH_SIZE", 4)
        self.tile_size = _env_int("TILE_SIZE", 1024)
        try:
            self.tile_overlap = float(_env_str("TILE_OVERLAP", "0.15") or "0.15")
        except ValueError:
            self.tile_overlap = 0.15

        # Mistral (analytical reports)
        self.mistral_api_key = _env_str("MISTRAL_API_KEY")
        self.mistral_model = _env_str("MISTRAL_MODEL", "mistral-small-latest")

    def resolve_database_url(self) -> str:
        """Return a SQLAlchemy-compatible URL, injecting the driver prefix if needed."""
        url = self.database_url
        if not url:
            return ""
        if "://" not in url:
            return url
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            # Default to the configured driver if not explicitly present.
            if "postgresql+psycopg" not in url and "postgresql+psycopg2" not in url:
                if self.database_driver == "psycopg2":
                    return "postgresql+psycopg2://" + url.split("://", 1)[1]
                return "postgresql+psycopg://" + url.split("://", 1)[1]
        return url


# A singleton for convenience.
settings = Settings()