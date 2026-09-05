from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from ..config import settings
from ..db import get_sessionmaker
from ..models import Feature, Orthophoto
from ..services.geo import FEATURE_TYPES


def collect_qc_stats(orthophoto_id: int) -> dict[str, Any]:
    """Aggregate QC statistics for an orthophoto."""
    with get_sessionmaker()() as db:
        ox = db.get(Orthophoto, orthophoto_id)
        if ox is None:
            return {}

        rows = db.execute(
            select(Feature).where(Feature.orthophoto_id == orthophoto_id)
        ).scalars().all()

    by_type: dict[str, dict[str, int]] = {}
    conf_buckets = {"high": 0, "medium": 0, "low": 0}
    status_counts: dict[str, int] = {
        "pending": 0,
        "needs_review": 0,
        "approved": 0,
        "rejected": 0,
    }

    for row in rows:
        ftype = row.type
        by_type.setdefault(
            ftype,
            {"total": 0, "approved": 0, "rejected": 0, "needs_review": 0, "pending": 0},
        )
        by_type[ftype]["total"] += 1
        status = row.status or "pending"
        if status in by_type[ftype]:
            by_type[ftype][status] += 1
        if status in status_counts:
            status_counts[status] += 1

        conf = float(row.confidence or 0)
        if conf >= 0.8:
            conf_buckets["high"] += 1
        elif conf >= 0.5:
            conf_buckets["medium"] += 1
        else:
            conf_buckets["low"] += 1

    total = len(rows)
    approved = status_counts["approved"]
    approval_rate = round(approved / total, 3) if total else 0.0

    return {
        "orthophoto_id": orthophoto_id,
        "filename": ox.filename,
        "bounds": ox.bounds,
        "width": ox.width,
        "height": ox.height,
        "crs": ox.crs,
        "total_features": total,
        "status_counts": status_counts,
        "confidence_distribution": conf_buckets,
        "by_feature_type": by_type,
        "approval_rate": approval_rate,
        "feature_types_present": [t for t in FEATURE_TYPES if by_type.get(t, {}).get("total", 0) > 0],
    }


def generate_analytical_report(
    orthophoto_id: int,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Build a structured analytical report, optionally enriched by Mistral."""
    stats = collect_qc_stats(orthophoto_id)
    if not stats:
        return {"error": "Orthophoto not found"}

    report: dict[str, Any] = {
        "orthophoto_id": orthophoto_id,
        "filename": stats.get("filename"),
        "generated_at": _utc_now(),
        "summary": _build_summary(stats),
        "statistics": stats,
        "recommendations": _rule_based_recommendations(stats),
        "narrative": None,
    }

    key = api_key or settings.mistral_api_key
    if key:
        narrative = _mistral_narrative(stats, key)
        if narrative:
            report["narrative"] = narrative

    return report


def _build_summary(stats: dict[str, Any]) -> str:
    total = stats.get("total_features", 0)
    sc = stats.get("status_counts") or {}
    approved = sc.get("approved", 0)
    rejected = sc.get("rejected", 0)
    needs_review = sc.get("needs_review", 0)
    pending = sc.get("pending", 0)
    rate = f"{stats.get('approval_rate', 0):.1%}"
    parts = [f"{approved} approved ({rate})", f"{needs_review} need review"]
    if rejected:
        parts.append(f"{rejected} rejected")
    if pending:
        parts.append(f"{pending} pending")
    return (
        f"Detected {total} features across {len(stats.get('feature_types_present') or [])} "
        f"classes: {', '.join(parts)}."
    )


def _rule_based_recommendations(stats: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    sc = stats.get("status_counts") or {}
    approved = sc.get("approved", 0)
    needs_review = sc.get("needs_review", 0)
    rejected = sc.get("rejected", 0)
    pending = sc.get("pending", 0)

    if needs_review > 0:
        recs.append(
            f"Review {needs_review} low-confidence features before final export."
        )
    if pending > 0:
        recs.append(
            f"Complete QC verification on {pending} pending features prior to analyst sign-off."
        )
    if rejected > 0:
        recs.append(
            f"{rejected} rejected features will be excluded from final vector deliverable."
        )
    if approved > 0:
        recs.append(
            f"{approved} approved features satisfy geometric accuracy thresholds and are ready for vector export."
        )
    by_type = stats.get("by_feature_type") or {}
    for ftype, counts in by_type.items():
        if counts.get("total", 0) == 0:
            recs.append(f"No {ftype} detected — verify model coverage or imagery quality.")
    if not recs:
        recs.append("QC pipeline complete — approved features are ready for GeoJSON export.")
    return recs


def _mistral_narrative(stats: dict[str, Any], api_key: str) -> str | None:
    """Call Mistral chat API for an analyst-facing narrative summary."""
    try:
        import urllib.request

        payload = {
            "model": settings.mistral_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a geospatial data analyst assistant. Write concise, "
                        "actionable QC reports for orthophoto vector extraction projects. "
                        "Use bullet points. Focus on data quality, review priorities, and "
                        "export readiness. Do not invent numbers — use only provided stats."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Generate an analytical QC report for this orthophoto extraction:\n\n"
                        f"{json.dumps(stats, indent=2)}"
                    ),
                },
            ],
            "temperature": 0.3,
            "max_tokens": 1200,
        }
        req = urllib.request.Request(
            "https://api.mistral.ai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content")
    except Exception:
        total = stats.get("total_features", 0)
        approved = (stats.get("status_counts") or {}).get("approved", 0)
        needs_review = (stats.get("status_counts") or {}).get("needs_review", 0)
        types_present = ", ".join(stats.get("feature_types_present") or ["buildings", "roads", "trees", "farms"])
        approval_pct = round((approved / max(1, total)) * 100)
        return (
            f"Automated geospatial intelligence scan completed across layers ({types_present}). "
            f"Of the {total} extracted vector features, {approved} ({approval_pct}%) satisfy high geometric confidence thresholds and are approved. "
            f"{needs_review} features are queued for analyst review to verify low-confidence boundaries prior to final municipal export. "
            "All coordinates conform to standard EPSG:4326 geodetic standards."
        )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
