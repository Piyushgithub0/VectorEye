from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ..config import settings
from ..services.report import collect_qc_stats, generate_analytical_report

router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/{orthophoto_id}")
def get_qc_stats(orthophoto_id: int) -> JSONResponse:
    """Return QC statistics for an orthophoto (no LLM call)."""
    stats = collect_qc_stats(orthophoto_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Orthophoto not found")
    return JSONResponse(stats)


@router.post("/{orthophoto_id}/generate")
def generate_report(
    orthophoto_id: int,
    mistral_api_key: str | None = Query(None, description="Override MISTRAL_API_KEY from env"),
) -> JSONResponse:
    """Generate a full analytical QC report, optionally with Mistral narrative."""
    key = mistral_api_key or settings.mistral_api_key
    report = generate_analytical_report(orthophoto_id, api_key=key)
    if report.get("error"):
        raise HTTPException(status_code=404, detail=report["error"])
    return JSONResponse(report)
