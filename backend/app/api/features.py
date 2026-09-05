from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from ..db import get_sessionmaker
from ..models import Feature
from ..schemas import BatchFeaturePatch, FeatureOut, FeaturePatch
from ..services.geo import FEATURE_TYPES

router = APIRouter(prefix="/api/features", tags=["features"])


@router.get("/{feature_type}")
def get_features(
    feature_type: str,
    min_confidence: float = Query(0.0, ge=0, le=1),
    status: str | None = Query(None),
    orthophoto_id: int | None = Query(None),
) -> dict[str, Any]:
    """Return a GeoJSON FeatureCollection for a single class.

    Query params support a minimum confidence floor, a status filter
    (pending | needs_review | approved | rejected) and an optional
    orthophoto_id to scope features to a specific uploaded image.
    """
    if feature_type not in FEATURE_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown feature type: {feature_type}")

    stmt = (
        select(Feature)
        .where(Feature.type == feature_type)
        .order_by(Feature.id)
    )
    if status:
        stmt = stmt.where(Feature.status == status)
    if orthophoto_id:
        stmt = stmt.where(Feature.orthophoto_id == orthophoto_id)

    with get_sessionmaker()() as db:
        rows = db.execute(stmt).scalars().all()

    features: list[dict[str, Any]] = []
    for row in rows:
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

    # Apply min_confidence filtering.
    if min_confidence > 0:
        features = [f for f in features if f["properties"]["confidence"] >= min_confidence]

    return {"type": "FeatureCollection", "features": features}


@router.post("/batch-status")
def batch_patch_features(patch: BatchFeaturePatch):
    """Batch approve / reject multiple features at once."""
    if not patch.feature_ids:
        return {"updated": 0, "status": patch.status}
    with get_sessionmaker()() as db:
        from sqlalchemy import update
        db.execute(
            update(Feature)
            .where(Feature.id.in_(patch.feature_ids))
            .values(status=patch.status)
        )
        db.commit()
    return {"updated": len(patch.feature_ids), "status": patch.status}


@router.patch("/{feature_id}", response_model=FeatureOut)
def patch_feature(feature_id: int, patch: FeaturePatch) -> FeatureOut:
    """Approve / reject / edit a single feature by id."""
    from ..config import settings

    with get_sessionmaker()() as db:
        row = db.get(Feature, feature_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Feature not found")
        if patch.status is not None:
            row.status = patch.status
        if patch.type is not None:
            row.type = patch.type
        if patch.className is not None:
            row.class_name = patch.className
        if patch.geometry is not None:
            geom_val: Any = patch.geometry
            if settings.database_url:
                try:
                    from shapely.geometry import shape
                    from geoalchemy2 import WKTElement
                    sh = shape(patch.geometry)
                    geom_val = WKTElement(sh.wkt, srid=4326)
                except Exception:
                    pass
            row.geometry = geom_val
        db.commit()
        db.refresh(row)
        return _feature_to_out(row)


def _feature_to_out(row: Feature) -> FeatureOut:
    return FeatureOut(
        id=row.id,
        type=row.type,
        className=row.class_name,
        confidence=row.confidence,
        status=row.status,
        geometry=_geom_geojson(row) or {"type": "Point", "coordinates": [0, 0]},
        created_at=str(row.created_at),
    )


def _geom_geojson(row: Feature) -> dict[str, Any] | None:
    if row.geometry is None:
        return None
    if isinstance(row.geometry, dict):
        return row.geometry
    try:
        if hasattr(row.geometry, "__geo_interface__"):
            return row.geometry.__geo_interface__
        from geoalchemy2.shape import to_shape
        from shapely.geometry import mapping

        return mapping(to_shape(row.geometry))
    except Exception:
        pass
    try:
        from shapely import wkt
        from shapely.geometry import mapping
        text_val = str(getattr(row.geometry, "data", row.geometry))
        return mapping(wkt.loads(text_val))
    except Exception:
        return None