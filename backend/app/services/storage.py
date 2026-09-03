from __future__ import annotations

import uuid
from pathlib import Path

from ..config import settings


UPLOAD_ROOT = settings.upload_dir


def ensure_upload_dir() -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return UPLOAD_ROOT


def save_upload(raw: bytes, original_filename: str) -> Path:
    """Persist an uploaded orthophoto and return its on-disk path.

    Files are stored under UPLOAD_DIR/<job-uuid>.<ext> to avoid collisions.
    """
    ensure_upload_dir()
    ext = Path(original_filename).suffix or ".tif"
    job = uuid.uuid4().hex
    path = UPLOAD_ROOT / f"{job}{ext}"
    path.write_bytes(raw)
    return path


def resolve_upload_path(stored: str) -> Path:
    p = Path(stored)
    if not p.is_absolute():
        p = settings.upload_dir / p
    return p