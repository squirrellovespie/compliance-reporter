# backend/src/api/routes/reports.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Iterable
import json
import traceback
import uuid

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import httpx

from engine.orchestrator import (
    run_report,
    run_report_stream,   # streamer (yields NDJSON lines)
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
    model: Optional[str] = None           # e.g., "gpt-4o-mini", "grok-4-latest"
    retrieval_strategy: Optional[str] = None  # "cosine" | "mmr" | "hybrid"

    # For webhook mode (Cloudflare-safe)
    webhook_url: Optional[str] = None     # if set, events are pushed to this URL


class GeneratePdfRequest(BaseModel):
    """
    Used when the frontend has final edited content and just wants a PDF.

    The frontend should send:
      - framework
      - firm
      - optional scope
      - sections: { "Section Name": "final edited text", ... }
      - optional findings: any dict; passed straight through to build_pdf
      - optional run_id: if you want a stable ID; else one is generated
    """
    framework: str
    firm: str
    scope: Optional[str] = None
    sections: Dict[str, str]
    findings: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None


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


def _run_stream_to_webhook(
    req: RunReportRequest,
    selected_sections: List[Dict[str, Any]],
    overarching: str,
    pre_run_id: str,
) -> None:
    """
    Background task used when webhook_url is provided.

    - Consumes run_report_stream(...)
    - For each event line, POSTs JSON to webhook_url
      and ensures run_id/framework/firm are always present.
    - At the end, emits a final { "event": "pdf_ready", "run_id": ... } event.
    """
    webhook_url = req.webhook_url
    if not webhook_url:
        return

    # Seed with pre-generated run_id so every event can be correlated
    run_id_seen: Optional[str] = pre_run_id

    try:
        stream: Iterable[str] = run_report_stream(
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
            run_id=pre_run_id,
        )

        with httpx.Client(timeout=10.0) as client:
            for line in stream:
                line = (line or "").strip()
                if not line:
                    continue

                try:
                    evt = json.loads(line)
                except Exception:
                    # if the line isn't valid JSON, just log and skip
                    print(f"[run_stream_to_webhook] Failed to parse line: {line!r}")
                    continue

                if evt.get("run_id"):
                    run_id_seen = evt["run_id"]

                payload = {
                    **evt,
                    "run_id": evt.get("run_id") or run_id_seen,
                    "framework": req.framework,
                    "firm": req.firm,
                }

                try:
                    client.post(webhook_url, json=payload)
                except Exception as post_err:
                    print(f"[run_stream_to_webhook] Webhook POST error: {post_err}")

            # Final notification: tell consumer that PDF is ready to be downloaded
            # via GET /reports/{run_id}/pdf
            if run_id_seen:
                try:
                    final_payload = {
                        "event": "pdf_ready",
                        "run_id": run_id_seen,
                        "framework": req.framework,
                        "firm": req.firm,
                    }
                    client.post(webhook_url, json=final_payload)
                except Exception as send_err:
                    print(f"[run_stream_to_webhook] Error sending final pdf_ready event: {send_err}")

    except Exception as e:
        traceback.print_exc()
        # Best-effort failure notification to the webhook
        try:
            if webhook_url:
                with httpx.Client(timeout=10.0) as client:
                    client.post(
                        webhook_url,
                        json={
                            "event": "report_failed",
                            "framework": req.framework,
                            "firm": req.firm,
                            "error": str(e),
                            "run_id": run_id_seen,
                        },
                    )
        except Exception as post_err:
            print(f"[run_stream_to_webhook] Error sending failure event: {post_err}")


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
def run_stream(req: RunReportRequest, background_tasks: BackgroundTasks):
    """
    Two modes:

    1) Local / dev streaming (no webhook_url):
       - Returns NDJSON StreamingResponse like before
       - Client reads events line-by-line until completion

    2) Webhook mode (Cloudflare-safe), when webhook_url is provided:
       - Spawns background task to stream events to webhook_url
       - Immediately returns a small JSON ack including run_id:
         { "status": "started", "webhook": true, "run_id": "...", ... }
    """
    # Pre-generate a run_id for correlation (especially for webhook mode)
    pre_run_id = f"{req.framework}-{req.firm}-{uuid.uuid4().hex[:12]}"

    # If a webhook URL is provided, use background webhook mode
    if req.webhook_url:
        try:
            selected_sections = _resolve_sections(req.framework, req.selected_section_ids)
            overarching = (req.overarching_prompt or "").strip() or get_overarching(req.framework)

            background_tasks.add_task(
                _run_stream_to_webhook,
                req,
                selected_sections,
                overarching,
                pre_run_id,
            )
            return {
                "status": "started",
                "webhook": True,
                "framework": req.framework,
                "firm": req.firm,
                "run_id": pre_run_id,
            }
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"/reports/run_stream webhook error: {str(e)}")

    # Otherwise, keep the original NDJSON streaming behavior
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

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


@router.post("/render_pdf")
def render_pdf(req: GeneratePdfRequest):
    """
    Given final edited content from the frontend, generate a PDF and return it.

    The structure matches what build_pdf already expects from a run:
      {
        "run_id": ...,
        "framework": ...,
        "firm": ...,
        "selected_sections": [...],
        "sections": { "Section Name": "text", ... },
        "findings": {...}
      }
    """
    try:
        run_id = req.run_id or f"{req.framework}-{req.firm}-manual-{uuid.uuid4().hex[:8]}"

        data: Dict[str, Any] = {
            "run_id": run_id,
            "framework": req.framework,
            "firm": req.firm,
            # Use the dict keys as selected_sections order (frontend can control ordering)
            "selected_sections": list(req.sections.keys()),
            "sections": req.sections,
            "findings": req.findings or {},
        }

        # Reuse the same RUNS_DIR so everything is consistent
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        out_pdf = RUNS_DIR / f"{run_id}.pdf"

        build_pdf(data, out_pdf)

        return FileResponse(
            str(out_pdf),
            media_type="application/pdf",
            filename=f"{run_id}.pdf",
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"/reports/render_pdf error: {str(e)}")


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
