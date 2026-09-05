from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Feature, Orthophoto


def geom_to_geojson(row: Feature) -> dict[str, Any] | None:
    """Convert a Feature row geometry to a GeoJSON dict."""
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


def build_analyst_properties(
    row: Feature,
    *,
    orthophoto: Orthophoto | None = None,
    export_scope: str = "approved",
) -> dict[str, Any]:
    """Analyst-friendly attribute schema for GIS / spreadsheet workflows."""
    conf = float(row.confidence or 0.0)
    tier = "high" if conf >= 0.8 else "medium" if conf >= 0.5 else "low"
    return {
        "feature_id": row.id,
        "orthophoto_id": row.orthophoto_id,
        "feature_type": row.type,
        "class_name": row.class_name,
        "confidence": round(conf, 4),
        "confidence_tier": tier,
        "qc_status": row.status,
        "review_action": _review_action(row.status),
        "source_filename": orthophoto.filename if orthophoto else "",
        "crs": "EPSG:4326",
        "export_scope": export_scope,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def _review_action(status: str) -> str:
    return {
        "approved": "accept",
        "rejected": "reject",
        "needs_review": "review",
        "pending": "pending",
    }.get(status, "pending")


def build_feature_collection(
    rows: list[Feature],
    *,
    orthophoto: Orthophoto | None = None,
    export_scope: str = "approved",
) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection suitable for analyst QC deliverables."""
    features: list[dict[str, Any]] = []
    for row in rows:
        if row.status == "rejected":
            continue
        geom = geom_to_geojson(row)
        if geom is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": row.id,
                "properties": build_analyst_properties(
                    row, orthophoto=orthophoto, export_scope=export_scope
                ),
                "geometry": geom,
            }
        )

    name = orthophoto.filename if orthophoto else "vectoreye"
    return {
        "type": "FeatureCollection",
        "name": name,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


def geojson_to_csv(fc: dict[str, Any]) -> str:
    """Flatten a FeatureCollection to CSV for spreadsheet analysts."""
    import csv
    import io

    buf = io.StringIO()
    fieldnames = [
        "feature_id",
        "orthophoto_id",
        "feature_type",
        "class_name",
        "confidence",
        "confidence_tier",
        "qc_status",
        "review_action",
        "geometry_type",
        "wkt",
        "source_filename",
        "exported_at",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        wkt = _geom_to_wkt(geom)
        writer.writerow(
            {
                "feature_id": props.get("feature_id"),
                "orthophoto_id": props.get("orthophoto_id"),
                "feature_type": props.get("feature_type"),
                "class_name": props.get("class_name"),
                "confidence": props.get("confidence"),
                "confidence_tier": props.get("confidence_tier"),
                "qc_status": props.get("qc_status"),
                "review_action": props.get("review_action"),
                "geometry_type": geom.get("type"),
                "wkt": wkt,
                "source_filename": props.get("source_filename"),
                "exported_at": props.get("exported_at"),
            }
        )
    return buf.getvalue()


def _geom_to_wkt(geom: dict[str, Any]) -> str:
    try:
        from shapely.geometry import shape

        return shape(geom).wkt
    except Exception:
        return ""


def geojson_to_kml(fc: dict[str, Any]) -> str:
    """Convert a GeoJSON FeatureCollection to standard KML vector format."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '  <Document>',
        f'    <name>{fc.get("name", "VectorEye")}</name>',
    ]
    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        feat_name = f"{props.get('class_name', 'Feature')} #{props.get('feature_id', '')}"
        desc = f"Type: {props.get('feature_type')}, Confidence: {props.get('confidence')}, Status: {props.get('qc_status')}"
        lines.append('    <Placemark>')
        lines.append(f'      <name>{feat_name}</name>')
        lines.append(f'      <description>{desc}</description>')
        if gtype == 'Point' and len(coords) >= 2:
            lines.append(f'      <Point><coordinates>{coords[0]},{coords[1]},0</coordinates></Point>')
        elif gtype == 'Polygon' and coords:
            ring_str = " ".join(f"{p[0]},{p[1]},0" for p in coords[0])
            lines.append(f'      <Polygon><outerBoundaryIs><LinearRing><coordinates>{ring_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
        elif gtype == 'LineString' and coords:
            line_str = " ".join(f"{p[0]},{p[1]},0" for p in coords)
            lines.append(f'      <LineString><coordinates>{line_str}</coordinates></LineString>')
        lines.append('    </Placemark>')
    lines.append('  </Document>')
    lines.append('</kml>')
    return "\n".join(lines)
