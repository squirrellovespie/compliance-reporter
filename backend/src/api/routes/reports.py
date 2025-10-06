# backend/src/api/routes/reports.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import traceback

from engine.orchestrator import run_report, load_run, RUNS_DIR
from engine.renderers.pdf_report import build_pdf
from engine.prompt_store import get_sections, get_overarching

router = APIRouter(prefix="/reports", tags=["reports"])


class RunReportRequest(BaseModel):
    framework: str
    firm: str
    scope: Optional[str] = None
    selected_section_ids: List[str]
    prompt_overrides: Dict[str, str] = {}
    overarching_prompt: Optional[str] = ""


def _resolve_sections(framework: str, selected_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Returns only the selected sections (sorted by position),
    raising if any id is unknown for the framework.
    """
    all_sections = get_sections(framework)  # [{id, name, position, default_prompt}, ...]
    index = {s["id"]: s for s in all_sections}
    result: List[Dict[str, Any]] = []
    for sid in selected_ids:
        if sid not in index:
            raise KeyError(f"Unknown section id for framework '{framework}': {sid}")
        result.append(index[sid])
    result.sort(key=lambda s: int(s.get("position", 0)))
    return result


@router.get("/sections/{framework}")
def list_sections(framework: str):
    """
    UI uses this to populate the section list + default prompts + overarching prompt.
    Reads from backend/src/guidelines/<framework>/prompts.yaml via prompt_store.py.
    """
    try:
        sections = get_sections(framework)
        over = get_overarching(framework)
        return {
            "framework": framework,
            "overarching_prompt": over,
            "sections": sections,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/run")
def run(req: RunReportRequest):
    """
    Run the report with selected sections (+ per-section overrides) and optional overarching prompt override.
    """
    try:
        selected_sections = _resolve_sections(req.framework, req.selected_section_ids)
        # UI override wins, else YAML value (from prompt_store)
        overarching = (req.overarching_prompt or "").strip() or get_overarching(req.framework)

        result = run_report(
            req.framework,
            req.firm,
            req.scope,
            selected_sections=selected_sections,
            prompt_overrides=req.prompt_overrides or {},
            overarching_prompt=overarching,
        )
        return {"run_id": result["run_id"], "result": result}
    except Exception as e:
        traceback.print_exc()
        # surface a concise message to the client
        raise HTTPException(status_code=500, detail=f"/reports/run error: {str(e)}")


@router.get("/{run_id}")
def get_run(run_id: str):
    try:
        return load_run(run_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/pdf")
def get_pdf(run_id: str):
    try:
        data = load_run(run_id)
        out_pdf = RUNS_DIR / f"{run_id}.pdf"
        build_pdf(data, out_pdf)
        return FileResponse(str(out_pdf), media_type="application/pdf", filename=f"{run_id}.pdf")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"/reports/{run_id}/pdf error: {str(e)}")
