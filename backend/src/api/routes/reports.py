from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from pathlib import Path
import traceback

from engine.orchestrator import run_report, load_run, RUNS_DIR
from engine.renderers.pdf_report import build_pdf
from fastapi.responses import FileResponse

router = APIRouter(prefix="/reports", tags=["reports"])

class RunReportBody(BaseModel):
    framework: str
    firm: str
    scope: Optional[str] = None
    selected_section_ids: List[str] = []
    prompt_overrides: Dict[str, str] = {}

@router.post("/run")
def run(body: RunReportBody):
    try:
        result = run_report(
            framework=body.framework,
            firm=body.firm,
            scope=body.scope,
            selected_section_ids=body.selected_section_ids,
            prompt_overrides=body.prompt_overrides,
        )
        return {"run_id": result["run_id"], "result": result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"/reports/run error: {e}")

@router.get("/{run_id}")
def get(run_id: str):
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
        return FileResponse(path=str(out_pdf), filename=f"{run_id}.pdf", media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
