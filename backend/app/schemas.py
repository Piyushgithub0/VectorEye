from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FeatureType = Literal["buildings", "roads", "water", "trees", "farms"]
FeatureStatus = Literal["pending", "needs_review", "approved", "rejected"]


class OrthophotoOut(BaseModel):
    """Matches the frontend Orthophoto interface."""

    id: int
    filename: str
    bounds: list[list[float]]  # [[south, west], [north, east]]
    width: int
    height: int


class FeatureOut(BaseModel):
    """Matches the frontend VectorFeature interface."""

    id: int
    type: FeatureType
    className: str = Field(alias="className")
    confidence: float
    status: FeatureStatus
    geometry: dict[str, Any]
    created_at: str

    model_config = {"populate_by_name": True}


    @classmethod
    def from_orm_row(cls, row: Any) -> "FeatureOut":
        """Build a FeatureOut from a raw SQLAlchemy row with a geometry WKB element."""
        properties = row._mapping.get("properties", {})
        geometry = _geom_to_geojson(row._mapping.get("geometry"))
        return cls(
            id=row._mapping["id"],
            type=row._mapping["type"],
            className=row._mapping.get("class_name") or properties.get("class", ""),
            confidence=float(row._mapping["confidence"]),
            status=row._mapping["status"],
            geometry=geometry,
            created_at=str(row._mapping["created_at"]),
        )


class FeaturePatch(BaseModel):
    """Approve/reject body for PATCH /api/features/{id}."""

    status: FeatureStatus


class UploadResponse(BaseModel):
    jobId: str = Field(alias="jobId")


class ExportGeojsonOut(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict[str, Any]]


def _geom_to_geojson(geom: Any) -> dict[str, Any]:
    """Convert a PostGIS geometry (WKBElement or dict) to a GeoJSON dict."""
    if geom is None:
        # Default small point so the frontend never fails to render.
        return {"type": "Point", "coordinates": [0, 0]}
    if isinstance(geom, dict):
        # Already a GeoJSON dict.
        return geom
    if hasattr(geom, "__geo_interface__"):
        return geom.__geo_interface__
    if hasattr(geom, "data"):
        from geoalchemy2.shape import to_shape

        try:
            shp = to_shape(geom)
            import shapely.geometry.mapping

            return shapely.geometry.mapping(shp)
        except Exception:
            return {"type": "Point", "coordinates": [0, 0]}
    return {"type": "Point", "coordinates": [0, 0]}