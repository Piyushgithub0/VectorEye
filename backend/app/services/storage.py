from __future__ import annotations

import uuid
from pathlib import Path

from ..config import settings


# Anchor to backend directory so uploads are always findable regardless of CWD.
if settings.upload_dir.is_absolute():
    UPLOAD_ROOT = settings.upload_dir
else:
    UPLOAD_ROOT = (settings.backend_dir / settings.upload_dir).resolve()


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
    """Resolve a stored filename/path to an absolute on-disk path."""
    p = Path(stored)
    if p.is_absolute() and p.exists():
        return p
    # Try the canonical UPLOAD_ROOT first (backend/uploads).
    candidate = UPLOAD_ROOT / p.name
    if candidate.exists():
        return candidate
    # Try repo root uploads directory.
    root_candidate = (settings.repo_root / "uploads" / p.name).resolve()
    if root_candidate.exists():
        return root_candidate
    # Try relative to CWD.
    cwd_candidate = (settings.upload_dir / p).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    if p.is_absolute():
        return p
    return candidate