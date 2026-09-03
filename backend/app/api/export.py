from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from ..db import get_sessionmaker
from ..models import Feature
from ..services.geo import FEATURE_TYPES

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{feature_type}")
def export_features(feature_type: str) -> Response:
    """Download all non-rejected features of a class as a GeoJSON file."""
    if feature_type not in FEATURE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown feature type: {feature_type}")

    with get_sessionmaker()() as db:
        rows = db.execute(
            select(Feature)
            .where(Feature.type == feature_type, Feature.status != "rejected")
            .order_by(Feature.id)
        ).scalars().all()

    features: list[dict[str, Any]] = []
    for row in rows:
        if row.geometry is None:
            continue
        geom = _geom_geojson(row)
        if geom is None:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": row.id,
                    "type": row.type,
                    "className": row.class_name,
                    "confidence": row.confidence,
                    "status": row.status,
                },
                "geometry": geom,
            }
        )

    fc = {"type": "FeatureCollection", "features": features}
    return JSONResponse(
        content=fc,
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{feature_type}-vectoreye.geojson"'},
    )


def _geom_geojson(row: Feature) -> dict[str, Any] | None:
    if hasattr(row.geometry, "__geo_interface__"):
        return row.geometry.__geo_interface__
    try:
        from geoalchemy2.shape import to_shape
        from shapely.geometry import mapping

        return mapping(to_shape(row.geometry))
    except Exception:
        return None