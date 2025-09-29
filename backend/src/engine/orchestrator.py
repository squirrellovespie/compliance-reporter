from __future__ import annotations
import json, time, traceback
from pathlib import Path
from typing import Any, Dict, List

from assessors.registry import get_assessor
from assessors.base import BuildContext, BaseFrameworkAssessor
from engine.sections_store import load_sections, SectionDef

RUNS_DIR = Path(__file__).resolve().parents[1] / "data" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

def _pick_sections(framework: str, selected_ids: List[str]) -> List[SectionDef]:
    all_defs = load_sections(framework)
    if not selected_ids:
        return all_defs
    sel = set(selected_ids)
    return [s for s in all_defs if s.id in sel]

def run_report(
    framework: str,
    firm: str,
    scope: str | None = None,
    selected_section_ids: List[str] | None = None,
    prompt_overrides: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    prompt_overrides = prompt_overrides or {}
    selected_section_ids = selected_section_ids or []

    # 1) Load assessor
    assessor_cls = get_assessor(framework)
    assessor: BaseFrameworkAssessor = assessor_cls()

    # 2) Findings
    try:
        ctx = BuildContext(firm=firm, scope=scope)
        findings = assessor.build_findings(ctx)
    except Exception as e:
        traceback.print_exc()
        etype = e.__class__.__name__
        raise RuntimeError(f"build_findings failed: {etype}: {e}")

    # 3) Sections
    try:
        section_defs = _pick_sections(framework, selected_section_ids)
        if not section_defs:
            raise RuntimeError("no sections defined for framework — seed or upsert sections first")

        sections_map: Dict[str, str] = {}
        for sec in section_defs:
            use_prompt = (prompt_overrides or {}).get(sec.id, sec.prompt or "")
            text = assessor.render_section_text(
                section_id=sec.id,
                section_name=sec.name,
                prompt=use_prompt,
                firm=firm,
                scope=scope,
                findings=findings,
            )
            sections_map[sec.name] = text

        run_id = f"{framework}-{firm}-{int(time.time())}"
        payload = {
            "run_id": run_id,
            "framework": framework,
            "firm": firm,
            "scope": scope,
            "selected_sections": [s.name for s in section_defs],
            "sections": sections_map,
            "findings": findings,
        }
        (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    except Exception as e:
        traceback.print_exc()
        etype = e.__class__.__name__
        raise RuntimeError(f"render sections failed: {etype}: {e}")

def load_run(run_id: str) -> Dict[str, Any]:
    fp = RUNS_DIR / f"{run_id}.json"
    if not fp.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    return json.loads(fp.read_text(encoding="utf-8"))
