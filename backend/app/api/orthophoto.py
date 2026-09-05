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
from ..config import settings
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
        if not bounds:
            bounds = [[18.52 - 0.015, 73.77 - 0.015], [18.52 + 0.015, 73.77 + 0.015]]
        record = {
            "width": info.get("width") or 1024,
            "height": info.get("height") or 1024,
            "crs": str(info.get("crs") or "EPSG:4326"),
            "west": bounds[0][1],
            "south": bounds[0][0],
            "east": bounds[1][1],
            "north": bounds[1][0],
        }
    except Exception:
        # Default non-georeferenced images to the demo coordinates (Pune)
        width, height = 1024, 1024
        try:
            from PIL import Image
            with Image.open(saved) as im:
                width, height = im.size
        except Exception:
            pass
        record = {
            "width": width,
            "height": height,
            "crs": "EPSG:4326",
            "west": 73.77 - 0.015,
            "south": 18.52 - 0.015,
            "east": 73.77 + 0.015,
            "north": 18.52 + 0.015,
        }

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
            pipeline = Pipeline(device=settings.ml_device)
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
    from ..config import settings
    from ..models import Feature
    from ..services.geo import geojson_to_array

    with get_sessionmaker()() as db:
        for f in raw_features:
            geom = f.get("geometry") or {}
            gtype = geom.get("type")
            pts = geojson_to_array(geom)
            if len(pts) == 0:
                continue
            geom_val: Any = geom
            if settings.database_url:
                wkt = _geometry_to_wkt(gtype, pts)
                if wkt is None:
                    continue
                from geoalchemy2 import WKTElement
                geom_val = WKTElement(wkt, srid=4326)

            feat_conf = float(f.get("confidence") or 0.5)
            feat = Feature(
                orthophoto_id=orthophoto_id,
                type=f["type"],
                class_name=f.get("class_name") or f["type"][:-1],
                confidence=feat_conf,
                status=f.get("status") or ("approved" if feat_conf >= 0.65 else "needs_review"),
                geometry=geom_val,
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


@router.get("/orthophoto/latest", response_model=OrthophotoOut)
def get_latest_orthophoto() -> Orthophoto:
    with get_sessionmaker()() as db:
        stmt = select(Orthophoto).order_by(Orthophoto.id.desc()).limit(20)
        records = db.execute(stmt).scalars().all()
        for ox in records:
            p = resolve_upload_path(ox.path)
            if p.exists():
                return ox
        if records:
            return records[0]
        raise HTTPException(status_code=404, detail="No orthophoto found")


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
    Caches the generated PNG on disk to avoid re-rendering large GeoTIFFs on every request.
    """
    from fastapi.responses import FileResponse, Response
    from ..services.storage import UPLOAD_ROOT

    cache_file = UPLOAD_ROOT / f"preview_{orthophoto_id}.png"
    if cache_file.exists():
        return FileResponse(
            str(cache_file),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

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
        import rasterio

        with rasterio.open(str(path)) as src:
            out_h = min(src.height, 2048)
            out_w = max(1, int(src.width * (out_h / max(src.height, 1))))
            read_count = min(src.count, 3)
            indexes = list(range(1, read_count + 1))
            data = src.read(indexes=indexes, out_shape=(read_count, out_h, out_w))
            if read_count == 1:
                data = np.repeat(data, 3, axis=0)
            data = np.transpose(data, (1, 2, 0))  # (H, W, 3)

            try:
                mask = src.read_masks(1, out_shape=(out_h, out_w))
            except Exception:
                mask = None

            if mask is not None:
                alpha = mask.astype(np.uint8)
            else:
                is_zero = np.all(data == 0, axis=-1)
                alpha = np.where(is_zero, 0, 255).astype(np.uint8)

            valid = alpha > 0
            if np.any(valid):
                valid_data = data[valid].astype(np.float32)
                lo, hi = np.percentile(valid_data, 2), np.percentile(valid_data, 98)
                if hi > lo:
                    stretched = np.clip((data.astype(np.float32) - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
                    data = np.where(alpha[..., None] > 0, stretched, data)

            rgba = np.dstack([data, alpha])
            img = Image.fromarray(rgba, mode="RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            try:
                cache_file.write_bytes(img_bytes)
            except Exception:
                pass
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        try:
            from PIL import Image
            import io

            with Image.open(str(path)) as im:
                im = im.convert("RGBA")
                im.thumbnail((2048, 2048))
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                try:
                    cache_file.write_bytes(img_bytes)
                except Exception:
                    pass
                return Response(
                    content=img_bytes,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except Exception:
            raise HTTPException(status_code=500, detail="Could not render image")