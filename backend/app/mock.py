"""Deterministic demo feature generator.

Mirrors the shape of the frontend's src/lib/mockData.ts so the UI's QC workflow
can be exercised before ML inference is wired up.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_demo_features(orthophoto_id: int, bounds: list[list[float]]) -> list[dict[str, Any]]:
    [[south, west], [north, east]] = bounds
    cx = (south + north) / 2
    cy = (west + east) / 2
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

    # Buildings
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
                    [cx + dx - w, cy + dy - h],
                    [cx + dx + w, cy + dy - h],
                    [cx + dx + w, cy + dy + h],
                    [cx + dx - w, cy + dy + h],
                    [cx + dx - w, cy + dy - h],
                ]],
            },
            conf,
            "approved" if conf > 0.75 else "pending",
        )

    # Roads
    road_pts = [
        [[cx - 0.015, cy - 0.012], [cx - 0.008, cy - 0.004], [cx, cy], [cx + 0.006, cy + 0.005], [cx + 0.012, cy + 0.01]],
        [[cx + 0.002, cy - 0.012], [cx + 0.003, cy - 0.006], [cx, cy], [cx - 0.005, cy + 0.006], [cx - 0.008, cy + 0.012]],
        [[cx - 0.012, cy - 0.012], [cx - 0.006, cy - 0.006], [cx - 0.002, cy], [cx - 0.006, cy + 0.006], [cx - 0.009, cy + 0.012]],
    ]
    for i, pts in enumerate(road_pts):
        make(
            "roads",
            {"type": "LineString", "coordinates": pts},
            0.6 + i * 0.08,
            "pending",
        )

    # Water river polygon
    make(
        "water",
        {
            "type": "Polygon",
            "coordinates": [[
                [cx + 0.009, cy - 0.012],
                [cx + 0.013, cy - 0.008],
                [cx + 0.014, cy - 0.003],
                [cx + 0.013, cy + 0.001],
                [cx + 0.014, cy + 0.005],
                [cx + 0.012, cy + 0.009],
                [cx + 0.009, cy + 0.012],
                [cx + 0.008, cy + 0.008],
                [cx + 0.009, cy + 0.004],
                [cx + 0.01, cy - 0.001],
                [cx + 0.009, cy - 0.006],
                [cx + 0.008, cy - 0.011],
                [cx + 0.009, cy - 0.012],
            ]],
        },
        0.87,
        "pending",
    )

    # Trees
    tree_centers = [
        (-0.012, -0.008), (-0.011, -0.005), (-0.014, -0.003),
        (-0.01, -0.001), (-0.013, 0.002), (-0.011, 0.005),
        (-0.015, 0.007), (-0.012, 0.009), (-0.009, 0.007),
    ]
    for i, (dx, dy) in enumerate(tree_centers):
        make(
            "trees",
            {
                "type": "Polygon",
                "coordinates": [[
                    [cx + dx - 0.0012, cy + dy - 0.0012],
                    [cx + dx + 0.0012, cy + dy - 0.0012],
                    [cx + dx + 0.0012, cy + dy + 0.0012],
                    [cx + dx - 0.0012, cy + dy + 0.0012],
                    [cx + dx - 0.0012, cy + dy - 0.0012],
                ]],
            },
            0.6 + (i % 3) * 0.1,
            "pending",
        )

    # Farms (forced needs_review)
    make(
        "farms",
        {
            "type": "Polygon",
            "coordinates": [[
                [cx - 0.012, cy + 0.013],
                [cx - 0.004, cy + 0.014],
                [cx - 0.003, cy + 0.018],
                [cx - 0.011, cy + 0.017],
                [cx - 0.012, cy + 0.013],
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
                [cx + 0.004, cy - 0.014],
                [cx + 0.012, cy - 0.015],
                [cx + 0.013, cy - 0.011],
                [cx + 0.005, cy - 0.01],
                [cx + 0.004, cy - 0.014],
            ]],
        },
        0.55,
        "needs_review",
    )

    return features