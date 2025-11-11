# backend/src/api/routes/reports.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Iterable
from pathlib import Path
import json
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from engine.orchestrator import (
    run_report,
    run_report_stream,   # <-- NEW: import streamer
    load_run,
    RUNS_DIR,
)
from engine.renderers.pdf_report import build_pdf
from engine.prompt_store import get_sections, get_overarching

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------- Request Models ----------
class RunReportRequest(BaseModel):
    framework: str
    firm: str
    scope: Optional[str] = None
    selected_section_ids: List[str]
    prompt_overrides: Dict[str, str] = {}
    overarching_prompt: Optional[str] = ""
    include_rag_debug: bool = False
    provider: str = "openai"              # e.g., "openai", "xai"
    model: Optional[str] = None           # e.g., "gpt-4o-mini", "grok-beta"
    retrieval_strategy: Optional[str] = None  # "cosine" | "mmr" | "hybrid"


# ---------- Helpers ----------
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


# ---------- Routes ----------
@router.get("/sections/{framework}")
def list_sections(framework: str):
    """
    UI uses this to populate the section list + default prompts + overarching prompt.
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
    Non-streaming run that returns the full result after generation completes.
    """
    try:
        selected_sections = _resolve_sections(req.framework, req.selected_section_ids)
        # UI override wins, else YAML value (from prompt_store)
        overarching = (req.overarching_prompt or "").strip() or get_overarching(req.framework)

        result = run_report(
            req.framework,
            req.firm,
            req.scope,
            provider=req.provider,
            model=req.model,
            selected_sections=selected_sections,
            prompt_overrides=req.prompt_overrides or {},
            overarching_prompt=overarching,
            include_rag_debug=req.include_rag_debug,
            retrieval_strategy=req.retrieval_strategy,
        )
        return {"run_id": result["run_id"], "result": result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"/reports/run error: {str(e)}")


@router.post("/run_stream")
def run_stream(req: RunReportRequest):
    """
    Streaming (NDJSON) run that yields progress events while the report is generated.

    Events (one JSON object per line):
      {"event":"start","run_id":...,"framework":...,"firm":...}
      {"event":"section_start","section_id":...,"section_name":...}
      {"event":"section_text","section_id":...,"section_name":...,"text":...}
      {"event":"end","run_id":...,"ok":true}
      {"event":"error","message":"..."}  # on failures
    """
    def _gen():
        try:
            selected_sections = _resolve_sections(req.framework, req.selected_section_ids)
            overarching = (req.overarching_prompt or "").strip() or get_overarching(req.framework)

            stream = run_report_stream(
                framework=req.framework,
                firm=req.firm,
                scope=req.scope,
                selected_sections=selected_sections,
                prompt_overrides=req.prompt_overrides or {},
                overarching_prompt=overarching,
                include_rag_debug=req.include_rag_debug,
                provider=req.provider,
                model=req.model,
                retrieval_strategy=req.retrieval_strategy,
            )
            for line in stream:
                # 'line' is already a JSON-encoded string with trailing "\n"
                yield line
        except Exception as e:
            traceback.print_exc()
            yield json.dumps({"event": "error", "message": str(e)}) + "\n"

    # NDJSON is simple and well-supported by browsers/fetch
    return StreamingResponse(_gen(), media_type="application/x-ndjson")


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
        return FileResponse(
            str(out_pdf),
            media_type="application/pdf",
            filename=f"{run_id}.pdf"
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"/reports/{run_id}/pdf error: {str(e)}")


@router.get("/{run_id}/rag_debug")
def get_rag_debug(run_id: str):
    try:
        data = load_run(run_id)
        return data.get("rag_debug", {})
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
