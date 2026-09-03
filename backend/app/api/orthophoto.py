from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_sessionmaker
from ..models import Orthophoto
from ..pipeline.pipeline import Pipeline
from ..schemas import OrthophotoOut, UploadResponse
from ..services.storage import resolve_upload_path, save_upload
from ..services.tiler import Tiler

router = APIRouter(prefix="/api", tags=["orthophoto"])


@router.post("/upload", response_model=UploadResponse)
async def upload_orthophoto(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Accept and process an orthophoto (GeoTIFF).

    Saves the file, records its metadata in the DB, then runs the pipeline
    to produce vector features. Returns a job id immediately.
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

    # Run the pipeline asynchronously-ish (background sync for now).
    _run_pipeline_into_db(saved, orthophoto_id)

    return {"jobId": str(orthophoto_id)}


def _run_pipeline_into_db(path: Path, orthophoto_id: int) -> None:
    """Run inference and insert the resulting features into the DB."""
    from ..models import Feature
    from ..services.geo import polygon_ring

    try:
        pipeline = Pipeline()
        raw_features = pipeline.run(str(path), orthophoto_id)
    except Exception:
        # Never let a model failure break the upload response.
        raw_features = []

    with get_sessionmaker()() as db:
        from geoalchemy2 import WKTElement

        for f in raw_features:
            ring = polygon_ring(f["geometry"])
            if not ring:
                continue
            wkt = _ring_to_wkt(ring)
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


def _ring_to_wkt(ring: list[list[float]]) -> str:
    """Build a POLYGON WKT string from a closed ring of [lon, lat] points."""
    pts = ", ".join(f"{lon} {lat}" for lon, lat in ring)
    return f"POLYGON(({pts}))"


@router.get("/orthophoto/{orthophoto_id}", response_model=OrthophotoOut)
def get_orthophoto(orthophoto_id: int) -> Orthophoto:
    with get_sessionmaker()() as db:
        ox = db.get(Orthophoto, orthophoto_id)
        if ox is None:
            raise HTTPException(status_code=404, detail="Orthophoto not found")
        return ox


@router.get("/orthophoto/{orthophoto_id}/image")
def serve_orthophoto_image(orthophoto_id: int):
    """Serve the original GeoTIFF file (used as the map overlay)."""
    with get_sessionmaker()() as db:
        ox = db.get(Orthophoto, orthophoto_id)
        if ox is None:
            raise HTTPException(status_code=404, detail="Orthophoto not found")
        path = resolve_upload_path(ox.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(str(path), media_type="image/tiff")