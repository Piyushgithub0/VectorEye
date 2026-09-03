from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_sessionmaker
from ..models import Orthophoto
from ..pipeline.pipeline import Pipeline
from ..schemas import OrthophotoOut, UploadResponse
from ..services.storage import resolve_upload_path, save_upload
from ..services.tiler import Tiler

router = APIRouter(prefix="/api", tags=["orthophoto"])

# In-memory progress store: jobId -> {"stage", "message", "progress", "done", "error"}
JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _job_status(job_id: str) -> dict[str, Any]:
    with _JOBS_LOCK:
        return dict(JOBS.get(job_id, {"stage": "queued", "message": "Waiting", "progress": 0, "done": False}))


def _set_job(job_id: str, **updates: Any) -> None:
    with _JOBS_LOCK:
        entry = JOBS.setdefault(job_id, {"done": False, "progress": 0})
        entry.update(updates)


@router.post("/upload", response_model=UploadResponse)
async def upload_orthophoto(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Accept and process an orthophoto (GeoTIFF).

    Saves the file, records its metadata in the DB, then runs the pipeline
    in the background to produce vector features. Returns a job id immediately.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Filename required")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    saved = save_upload(raw, file.filename)

    # Inspect georeferencing with the tiler.
    record: dict[str, Any] = {}
    try:
        tiler = Tiler(saved)
        info = tiler.info()
        bounds = info.get("bounds")
        record = {
            "width": info.get("width") or 0,
            "height": info.get("height") or 0,
            "crs": info.get("crs") or "EPSG:32643",
            "west": bounds[0][1] if bounds else 0.0,
            "south": bounds[0][0] if bounds else 0.0,
            "east": bounds[1][1] if bounds else 0.0,
            "north": bounds[1][0] if bounds else 0.0,
        }
    except Exception:
        # Not gated: non-georeferenced files still record with zeros.
        record = {"width": 0, "height": 0, "crs": "EPSG:32643",
                  "west": 0.0, "south": 0.0, "east": 0.0, "north": 0.0}

    with get_sessionmaker()() as db:
        ox = Orthophoto(
            filename=file.filename,
            path=saved.name,
            crs=record["crs"],
            width=record["width"],
            height=record["height"],
            west=record["west"],
            south=record["south"],
            east=record["east"],
            north=record["north"],
        )
        db.add(ox)
        db.commit()
        db.refresh(ox)
        orthophoto_id = ox.id

    job_id = str(orthophoto_id)
    _set_job(job_id, stage="queued", message="Starting pipeline", progress=0, done=False, error=None)

    def progress_cb(stage: str, message: str, pct: float | None) -> None:
        _set_job(
            job_id,
            stage=stage,
            message=message,
            progress=max(0, min(100, int(pct or 0))),
        )

    def work() -> None:
        try:
            _set_job(job_id, stage="tiling", message="Running pipeline", progress=2)
            pipeline = Pipeline()
            raw_features = pipeline.run(str(saved), orthophoto_id, progress=progress_cb)
            _insert_features(orthophoto_id, raw_features)
            _set_job(job_id, done=True, stage="complete", progress=100)
        except Exception as exc:  # pragma: no cover - defensive
            _set_job(job_id, done=True, stage="error", error=str(exc), progress=100)

    background_tasks.add_task(work)
    return {"jobId": job_id}


@router.get("/jobs/{job_id}/status")
def job_status(job_id: str) -> JSONResponse:
    return JSONResponse(_job_status(job_id))


def _insert_features(orthophoto_id: int, raw_features: list[dict[str, Any]]) -> None:
    """Insert the vector features produced by the pipeline into the DB."""
    from geoalchemy2 import WKTElement
    from ..models import Feature
    from ..services.geo import geojson_to_array

    with get_sessionmaker()() as db:
        for f in raw_features:
            geom = f.get("geometry") or {}
            gtype = geom.get("type")
            pts = geojson_to_array(geom)
            if len(pts) == 0:
                continue
            wkt = _geometry_to_wkt(gtype, pts)
            if wkt is None:
                continue
            feat = Feature(
                orthophoto_id=orthophoto_id,
                type=f["type"],
                class_name=f.get("class_name") or f["type"][:-1],
                confidence=f.get("confidence") or 0.5,
                status=f.get("status") or "pending",
                geometry=WKTElement(wkt, srid=4326),
            )
            db.add(feat)
        db.commit()


def _geometry_to_wkt(gtype: str | None, pts: Any) -> str | None:
    """Build a PostGIS WKT string for a simple geometry from a Nx2 [lon, lat] array.

    Returns None for degenerate/invalid geometries so they get skipped.
    """
    import numpy as np

    pts = np.asarray(pts, dtype=float)
    if pts.ndim != 2 or len(pts) < 2:
        return None
    if gtype == "Point":
        x, y = pts[0]
        return f"POINT({x} {y})"
    if gtype == "LineString":
        # Reject degenerate (single-point / all-identical) lines.
        if len(np.unique(pts, axis=0)) < 2:
            return None
        parts = ", ".join(f"{x} {y}" for x, y in pts)
        return f"LINESTRING({parts})"
    # Default to polygon; force the ring to be closed (PostGIS requirement).
    ring = _closed_ring(pts)
    if len(ring) < 4:
        return None
    parts = ", ".join(f"{x} {y}" for x, y in ring)
    return f"POLYGON(({parts}))"


def _closed_ring(pts: Any) -> list[list[float]]:
    """Return pts as a closed exterior ring (first point repeated at the end).

    Tolerance is absolute-only (rtol=0) so that nearby-but-distinct projected
    lon/lat vertices are kept; the default relative tolerance collapses real
    georeferenced edges (large coordinate magnitudes) into a single point.
    """
    import numpy as np

    tol = dict(rtol=0, atol=1e-9)

    ring = [[float(x), float(y)] for x, y in pts]
    if len(ring) >= 2 and not np.allclose(ring[0], ring[-1], **tol):
        ring.append([ring[0][0], ring[0][1]])
    # Drop duplicate points to avoid self-intersection.
    kept: list[list[float]] = []
    for p in ring:
        if not kept or not np.allclose(kept[-1], p, **tol):
            kept.append(p)
    if len(kept) >= 2 and np.allclose(kept[0], kept[-1], **tol):
        kept = kept[:-1]
    # Re-close after dedup.
    if len(kept) >= 2 and not np.allclose(kept[0], kept[-1], **tol):
        kept.append([kept[0][0], kept[0][1]])
    return kept


@router.get("/orthophoto/{orthophoto_id}", response_model=OrthophotoOut)
def get_orthophoto(orthophoto_id: int) -> Orthophoto:
    with get_sessionmaker()() as db:
        ox = db.get(Orthophoto, orthophoto_id)
        if ox is None:
            raise HTTPException(status_code=404, detail="Orthophoto not found")
        return ox


@router.get("/orthophoto/{orthophoto_id}/image")
def serve_orthophoto_image(orthophoto_id: int):
    """Serve the orthophoto as a browser-renderable PNG (not GeoTIFF).

    Browsers cannot decode GeoTIFF, so we rasterize the central window to RGB PNG
    with a contrast stretch so the picture is actually visible on the map.
    """
    from fastapi.responses import Response

    with get_sessionmaker()() as db:
        ox = db.get(Orthophoto, orthophoto_id)
        if ox is None:
            raise HTTPException(status_code=404, detail="Orthophoto not found")
        path = resolve_upload_path(ox.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Image file missing")
        w, h = ox.width, ox.height

    try:
        import numpy as np
        from PIL import Image
        import io

        tiler = Tiler(str(path))
        width = w or 2048
        if width <= 0:
            width = 2048
        limit = 2048
        if width > limit:
            factor = width / limit
            crop_px = limit
        else:
            factor = 1.0
            crop_px = width
        info = tiler.info()
        bounds = info.get("bounds")
        if bounds:
            [[s2, w2], [n2, e2]] = bounds
            center_lat = (s2 + n2) / 2
            center_lon = (w2 + e2) / 2
        else:
            center_lon, center_lat, crop_px = ox.west or 0.0, ox.south or 0.0, 512
        crop, _ = tiler.crop_window(center_lon, center_lat, crop_px)

        data = np.asarray(crop)
        h2, w2 = 0, 0
        if data.ndim == 3 and data.shape[0] <= 4:
            data = np.transpose(data, (1, 2, 0))  # (C,H,W) -> (H,W,C)
        if data.ndim == 3:
            h2, w2 = data.shape[0], data.shape[1]
            data = data[..., :3]
        elif data.ndim == 2:
            h2, w2 = data.shape
            data = np.stack([data] * 3, axis=-1)

        if data.size == 0 or w2 == 0 or h2 == 0:
            raise ValueError("empty crop")
        data = np.asarray(data, dtype=np.float32)
        lo, hi = np.percentile(data, 2), np.percentile(data, 98)
        if hi > lo:
            data = (data - lo) / (hi - lo)
        data = np.clip(data * 255.0, 0, 255).astype(np.uint8)

        img = Image.fromarray(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/png")
    except Exception:
        raise HTTPException(status_code=500, detail="Could not render image")