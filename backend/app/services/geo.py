from __future__ import annotations

from typing import Any

import numpy as np

# Ordered inference classes (matches the frontend FeatureType).
FEATURE_TYPES = ["buildings", "roads", "water", "trees", "farms"]


def geojson_to_array(geometry: dict[str, Any]) -> np.ndarray:
    """Extract a Nx2 array of [lon, lat] coordinates from a simple GeoJSON geometry.

    Supports Point, LineString and Polygon (exterior ring only for polygons).
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Point":
        return np.asarray([coords], dtype=float)
    if gtype in ("LineString", "MultiPoint"):
        return np.asarray(coords, dtype=float)
    if gtype in ("Polygon", "MultiLineString"):
        # Exterior ring of the first polygon / first line.
        return np.asarray(coords[0], dtype=float)
    if gtype == "MultiPolygon":
        return np.asarray(coords[0][0], dtype=float)
    return np.empty((0, 2), dtype=float)


def polygon_ring(geometry: dict[str, Any]) -> list[list[float]]:
    """Return the exterior ring of a Polygon geometry as a closed list of [lon, lat]."""
    coords = geojson_to_array(geometry)
    if len(coords) == 0:
        return []
    return coords.tolist()


def make_bounds(
    west: float, south: float, east: float, north: float
) -> list[list[float]]:
    """Return bounds in the [[south, west], [north, east]] order the UI expects."""
    min_lat = float(min(south, north))
    max_lat = float(max(south, north))
    min_lon = float(min(west, east))
    max_lon = float(max(west, east))
    return [[min_lat, min_lon], [max_lat, max_lon]]