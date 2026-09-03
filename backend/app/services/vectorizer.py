from __future__ import annotations

from typing import Any

import numpy as np

from .geo import polygon_ring


class Vectorizer:
    """Convert a raster probability/mask into GeoJSON polygon features.

    Given a binary mask and a georeferencing context (affine transform mapping
    pixel -> Geo CRS), this extracts polygons, simplifies them and emits them as
    EPSG:4326 GeoJSON that the frontend can render directly.
    """

    def __init__(
        self,
        *,
        simplify_tolerance: float = 0,
        min_area_px: int = 8,
        min_points: int = 4,
    ) -> None:
        self.simplify_tolerance = simplify_tolerance
        self.min_area_px = min_area_px
        self.min_points = min_points

    def mask_to_geojson(
        self,
        mask: np.ndarray,
        *,
        geo_transform: Any | None,
        class_name: str = "",
        confidence: float = 0.5,
        feature_type: str = "buildings",
    ) -> list[dict[str, Any]]:
        """Return a list of GeoJSON Feature dicts (EPSG:4326) from a 2D mask."""
        features: list[dict[str, Any]] = []
        try:
            from skimage.measure import find_contours
        except ImportError:
            return features

        mask = np.asarray(mask)
        if mask.ndim != 2:
            return features

        # Threshold at 0.5 to produce a binary mask.
        binary = (mask > 0.5).astype(np.uint8)

        if binary.sum() < self.min_area_px:
            return features

        # get_pixels Affine for mask coords -> Geo coords.
        if geo_transform is None:
            # Identity pixel->lon/lat fallback (test/demo data).
            geo_t = [1, 0, 0, 0, -1, 0]  # px -> (lon, lat) scaling placeholder
        else:
            geo_t = geo_transform

        for contour in find_contours(binary, level=0.5):
            if len(contour) < self.min_points:
                continue
            ring = _pixel_ring_to_geojson(contour, geo_t)
            if len(ring) < self.min_points:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "class": class_name,
                        "confidence": float(confidence),
                        "type": feature_type,
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [ring],
                    },
                }
            )
        return features

    def box_to_geojson(
        self,
        box: Any,
        *,
        geo_transform: Any | None,
        class_name: str = "",
        confidence: float = 0.5,
        feature_type: str = "buildings",
    ) -> list[dict[str, Any]]:
        """Return a GeoJSON rectangle Polygon (EPSG:4326) from a (x1,y1,x2,y2) box.

        The box coords are in pixel space of the orthophoto crop. They are mapped
        into lon/lat via the same GDAL-style affine as masks.
        """
        try:
            x1, y1, x2, y2 = (float(v) for v in box)
        except (TypeError, ValueError):
            return []
        if x2 - x1 < 2 or y2 - y1 < 2:
            return []

        geo_t = geo_transform or [1, 0, 0, 0, -1, 0]
        a, b, c, d, e, f = geo_t[0], geo_t[1], geo_t[2], geo_t[3], geo_t[4], geo_t[5]
        # Pixel (col,row) -> (lon, lat).
        def to_xy(col: float, row: float) -> tuple[float, float]:
            x = a * col + b * row + c
            y = d * col + e * row + f
            return float(x), float(y)

        # Polygon corners in (lon, lat) order.
        ring = [
            list(to_xy(x1, y1)),
            list(to_xy(x2, y1)),
            list(to_xy(x2, y2)),
            list(to_xy(x1, y2)),
            list(to_xy(x1, y1)),
        ]
        return [
            {
                "type": "Feature",
                "properties": {
                    "class": class_name,
                    "confidence": float(confidence),
                    "type": feature_type,
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        ]

    def line_to_geojson(
        self,
        points: list[list[float]],
        *,
        geo_transform: Any | None,
        class_name: str = "",
        confidence: float = 0.5,
        feature_type: str = "roads",
    ) -> list[dict[str, Any]]:
        """Return a GeoJSON LineString (EPSG:4326) from pixel-space polyline points.

        Points are [(col, row), ...] in the crop; each is mapped to (lon, lat)
        with the same GDAL-style affine used for masks/boxes.
        """
        if not points or len(points) < 2:
            return []
        geo_t = geo_transform or [1, 0, 0, 0, -1, 0]
        a, b, c, d, e, f = geo_t[0], geo_t[1], geo_t[2], geo_t[3], geo_t[4], geo_t[5]

        def to_xy(col: float, row: float) -> list[float]:
            x = a * col + b * row + c
            y = d * col + e * row + f
            return [float(x), float(y)]

        coords = []
        seen: set[tuple[float, float]] = set()
        for col, row in points:
            pt = to_xy(col, row)
            key = (round(pt[0], 9), round(pt[1], 9))
            if key in seen:
                continue
            seen.add(key)
            coords.append(pt)
        if len(coords) < 2:
            return []
        return [
            {
                "type": "Feature",
                "properties": {
                    "class": class_name,
                    "confidence": float(confidence),
                    "type": feature_type,
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        ]


def _pixel_ring_to_geojson(contour: np.ndarray, geo_t: Any) -> list[list[float]]:
    """Map a find_contours output (row, col) ring to (lon, lat) ring.

    geo_t is a 6-tuple GDAL-style affine: [c, a, b, f, d, e] mapping
    (col, row) -> (x, y) via:
        x = a * col + b * row + c
        y = d * col + e * row + f
    This is the standard rasterio transform.to_gdal() layout.
    """
    a, b, c, d, e, f = geo_t[0], geo_t[1], geo_t[2], geo_t[3], geo_t[4], geo_t[5]
    pts: list[list[float]] = []
    for row, col in contour:
        x = a * col + b * row + c
        y = d * col + e * row + f
        pts.append([float(x), float(y)])
    # Close the ring.
    if pts and (pts[0][0] != pts[-1][0] or pts[0][1] != pts[-1][1]):
        pts.append([pts[0][0], pts[0][1]])
    return pts