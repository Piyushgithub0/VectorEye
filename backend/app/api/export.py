from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import select

from ..db import get_sessionmaker
from ..models import Feature, Orthophoto
from ..services.export_geo import build_feature_collection, geojson_to_csv, geojson_to_kml
from ..services.geo import FEATURE_TYPES

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{feature_type}")
def export_features(
    feature_type: str,
    orthophoto_id: int | None = Query(None, description="Scope export to one orthophoto"),
    status: str | None = Query(
        "all",
        description="QC status filter: all | approved | pending | needs_review",
    ),
    min_confidence: float = Query(0.0, ge=0, le=1),
    format: str = Query("geojson", description="geojson | csv | kml"),
) -> Response:
    """Download analyst-ready vector features (all extracted vectors by default)."""
    if feature_type != "all" and feature_type not in FEATURE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown feature type: {feature_type}")

    with get_sessionmaker()() as db:
        ox = db.get(Orthophoto, orthophoto_id) if orthophoto_id else None

        stmt = select(Feature).order_by(Feature.id)
        if feature_type != "all":
            stmt = stmt.where(Feature.type == feature_type)
        if orthophoto_id is not None:
            stmt = stmt.where(Feature.orthophoto_id == orthophoto_id)
        if status and status != "all":
            stmt = stmt.where(Feature.status == status)
        else:
            stmt = stmt.where(Feature.status != "rejected")

        rows = db.execute(stmt).scalars().all()

    if min_confidence > 0:
        rows = [r for r in rows if float(r.confidence or 0) >= min_confidence]

    export_scope = status or "all"
    fc = build_feature_collection(rows, orthophoto=ox, export_scope=export_scope)

    base_name = _export_basename(ox, feature_type, export_scope)

    if format == "csv":
        csv_text = geojson_to_csv(fc)
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.csv"'},
        )

    if format == "kml":
        kml_text = geojson_to_kml(fc)
        return PlainTextResponse(
            content=kml_text,
            media_type="application/vnd.google-earth.kml+xml",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.kml"'},
        )

    return JSONResponse(
        content=fc,
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{base_name}.geojson"'},
    )


def _export_basename(ox: Orthophoto | None, feature_type: str, scope: str) -> str:
    stem = (ox.filename if ox else "vectoreye").rsplit(".", 1)[0]
    type_part = feature_type if feature_type != "all" else "all-features"
    return f"{stem}-{type_part}-{scope}"
