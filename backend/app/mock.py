"""Deterministic demo feature generator.

Mirrors the shape of the frontend's src/lib/mockData.ts so the UI's QC workflow
can be exercised before ML inference is wired up.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_demo_features(orthophoto_id: int, bounds: list[list[float]]) -> list[dict[str, Any]]:
    [[south, west], [north, east]] = bounds
    clat = (south + north) / 2
    clon = (west + east) / 2
    span_lat = max(abs(north - south), 0.0005)
    span_lon = max(abs(east - west), 0.0005)
    # Scale coordinates so they stay safely within the orthophoto image boundaries
    # Authored deltas were based on ~0.04 deg span
    sx = (span_lon * 0.8) / 0.04
    sy = (span_lat * 0.8) / 0.04

    features: list[dict[str, Any]] = []
    counter = {"id": 1}

    def make(
        ftype: str,
        geometry: dict[str, Any],
        confidence: float,
        status: str = "pending",
    ) -> dict[str, Any]:
        if ftype == "farms":
            status = "needs_review"
        feat = {
            "id": counter["id"],
            "orthophoto_id": orthophoto_id,
            "type": ftype,
            "class_name": ftype[:-1],
            "confidence": round(confidence, 3),
            "status": status,
            "geometry": geometry,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        counter["id"] += 1
        features.append(feat)
        return feat

    # Buildings (GeoJSON coordinates format: [lon, lat])
    building_specs = [
        (0.001, 0.001, 0.0008, 0.0006, 0.72),
        (0.004, 0.003, 0.0007, 0.0008, 0.68),
        (-0.003, -0.001, 0.0006, 0.0007, 0.81),
        (0.006, -0.004, 0.001, 0.0005, 0.65),
        (-0.005, 0.004, 0.0005, 0.001, 0.77),
        (0.001, -0.006, 0.0012, 0.0006, 0.7),
        (0.008, 0.001, 0.0006, 0.0011, 0.74),
        (-0.004, 0.007, 0.0004, 0.0009, 0.6),
        (0.004, -0.002, 0.0009, 0.0005, 0.83),
        (-0.001, 0.002, 0.0005, 0.0007, 0.66),
    ]
    for dx, dy, w, h, conf in building_specs:
        make(
            "buildings",
            {
                "type": "Polygon",
                "coordinates": [[
                    [clon + (dx - w) * sx, clat + (dy - h) * sy],
                    [clon + (dx + w) * sx, clat + (dy - h) * sy],
                    [clon + (dx + w) * sx, clat + (dy + h) * sy],
                    [clon + (dx - w) * sx, clat + (dy + h) * sy],
                    [clon + (dx - w) * sx, clat + (dy - h) * sy],
                ]],
            },
            conf,
            "approved" if conf > 0.75 else "pending",
        )

    # Roads: [lon, lat]
    road_pts = [
        [
            [clon - 0.015 * sx, clat - 0.012 * sy],
            [clon - 0.008 * sx, clat - 0.004 * sy],
            [clon, clat],
            [clon + 0.006 * sx, clat + 0.005 * sy],
            [clon + 0.012 * sx, clat + 0.01 * sy],
        ],
        [
            [clon + 0.002 * sx, clat - 0.012 * sy],
            [clon + 0.003 * sx, clat - 0.006 * sy],
            [clon, clat],
            [clon - 0.005 * sx, clat + 0.006 * sy],
            [clon - 0.008 * sx, clat + 0.012 * sy],
        ],
        [
            [clon - 0.012 * sx, clat - 0.012 * sy],
            [clon - 0.006 * sx, clat - 0.006 * sy],
            [clon - 0.002 * sx, clat],
            [clon - 0.006 * sx, clat + 0.006 * sy],
            [clon - 0.009 * sx, clat + 0.012 * sy],
        ],
    ]
    for i, pts in enumerate(road_pts):
        make(
            "roads",
            {"type": "LineString", "coordinates": pts},
            0.6 + i * 0.08,
            "pending",
        )

    # Water river polygon: [lon, lat]
    make(
        "water",
        {
            "type": "Polygon",
            "coordinates": [[
                [clon + 0.009 * sx, clat - 0.012 * sy],
                [clon + 0.013 * sx, clat - 0.008 * sy],
                [clon + 0.014 * sx, clat - 0.003 * sy],
                [clon + 0.013 * sx, clat + 0.001 * sy],
                [clon + 0.014 * sx, clat + 0.005 * sy],
                [clon + 0.012 * sx, clat + 0.009 * sy],
                [clon + 0.009 * sx, clat + 0.012 * sy],
                [clon + 0.008 * sx, clat + 0.008 * sy],
                [clon + 0.009 * sx, clat + 0.004 * sy],
                [clon + 0.010 * sx, clat - 0.001 * sy],
                [clon + 0.009 * sx, clat - 0.006 * sy],
                [clon + 0.008 * sx, clat - 0.011 * sy],
                [clon + 0.009 * sx, clat - 0.012 * sy],
            ]],
        },
        0.87,
        "pending",
    )

    # Trees: [lon, lat]
    tree_centers = [
        (-0.012, -0.008), (-0.011, -0.005), (-0.014, -0.003),
        (-0.010, -0.001), (-0.013, 0.002), (-0.011, 0.005),
        (-0.015, 0.007), (-0.012, 0.009), (-0.009, 0.007),
    ]
    for i, (dx, dy) in enumerate(tree_centers):
        make(
            "trees",
            {
                "type": "Polygon",
                "coordinates": [[
                    [clon + (dx - 0.0012) * sx, clat + (dy - 0.0012) * sy],
                    [clon + (dx + 0.0012) * sx, clat + (dy - 0.0012) * sy],
                    [clon + (dx + 0.0012) * sx, clat + (dy + 0.0012) * sy],
                    [clon + (dx - 0.0012) * sx, clat + (dy + 0.0012) * sy],
                    [clon + (dx - 0.0012) * sx, clat + (dy - 0.0012) * sy],
                ]],
            },
            0.6 + (i % 3) * 0.1,
            "pending",
        )

    # Farms: [lon, lat]
    make(
        "farms",
        {
            "type": "Polygon",
            "coordinates": [[
                [clon - 0.012 * sx, clat + 0.013 * sy],
                [clon - 0.004 * sx, clat + 0.014 * sy],
                [clon - 0.003 * sx, clat + 0.018 * sy],
                [clon - 0.011 * sx, clat + 0.017 * sy],
                [clon - 0.012 * sx, clat + 0.013 * sy],
            ]],
        },
        0.62,
        "needs_review",
    )
    make(
        "farms",
        {
            "type": "Polygon",
            "coordinates": [[
                [clon + 0.004 * sx, clat - 0.014 * sy],
                [clon + 0.012 * sx, clat - 0.015 * sy],
                [clon + 0.013 * sx, clat - 0.011 * sy],
                [clon + 0.005 * sx, clat - 0.010 * sy],
                [clon + 0.004 * sx, clat - 0.014 * sy],
            ]],
        },
        0.55,
        "needs_review",
    )

    return features