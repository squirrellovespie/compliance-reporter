from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
from pathlib import Path
import os, json

from assessors.registry import get_assessor
from assessors.base import BuildContext, BaseFrameworkAssessor

from services.ai_client import chat_complete
from services.vector_langchain import query as vs_query

RUNS_DIR = Path(os.getenv("RUNS_PATH", "./src/data/runs")).resolve()
RUNS_DIR.mkdir(parents=True, exist_ok=True)

MEM_SUMMARY_TOKENS = 350
MEM_POINTS_LIMIT   = 12
RETRIEVE_K         = 8

@dataclass
class RollingMemory:
    narrative_summary: str = ""
    points: List[str] = field(default_factory=list)
    used_evidence: Set[Tuple[str, int]] = field(default_factory=set)

    def to_prompt_block(self) -> str:
        parts: List[str] = []
        if self.narrative_summary:
            parts.append(f"Context so far (do not repeat): {self.narrative_summary}")
        if self.points:
            bullets = "\n".join(f"- {p}" for p in self.points[:MEM_POINTS_LIMIT])
            parts.append(f"Key points already covered (avoid repetition):\n{bullets}")
        if self.used_evidence:
            parts.append(
                "Evidence already cited (avoid reusing unless critical): " +
                ", ".join(f"{d}@p{p}" for d, p in list(self.used_evidence)[:15]) +
                ("…" if len(self.used_evidence) > 15 else "")
            )
        return "\n\n".join(parts)

def _summarize_text_for_memory(
    text: str,
    *,
    provider: str,
    model: Optional[str],
) -> Dict[str, Any]:
    """
    Summarize section to compact memory: {narrative, bullets[]}.
    For xAI we avoid response_format and enforce JSON via prompt instructions.
    """
    prompt = (
        "Summarize the following section into: "
        "1) one 150–250 token narrative paragraph (no new facts), and "
        "2) 5–7 concise bullets. "
        "Return ONLY valid JSON with keys: narrative (string), bullets (array of strings)."
    )
    messages = [
        {"role": "system", "content": "You are a precise summarizer for an audit report. Return only JSON."},
        {"role": "user", "content": prompt + "\n\n---\n" + text.strip()},
    ]
    # Use JSON mode only for OpenAI; for xAI we rely on prompt
    resp = chat_complete(
        provider=provider, model=model,
        messages=messages,
        response_format=("json_object" if provider == "openai" else None),
        temperature=0.2, max_tokens=600
    )
    try:
        return json.loads(resp)
    except Exception:
        return {"narrative": "", "bullets": []}

def _retrieve_chunks(
    framework: str,
    firm: str,
    query_text: str,
    used_ev: Set[Tuple[str,int]],
    k: int = REVEAL_K if (REVEAL_K:=RETRIEVE_K) else RETRIEVE_K,
) -> List[Dict[str, Any]]:
    pool = []
    def _pull(collection: str, source_label: str):
        try:
            rows = vs_query(collection_name=collection, text=query_text, k=k*2) or []
            for r in rows:
                m = r.get("metadata", {}) or {}
                doc_id = m.get("doc_id") or m.get("source_pdf") or source_label
                page = int(m.get("page", 0))
                pool.append({
                    "text": r.get("text", "") or "",
                    "metadata": {"doc_id": doc_id, "page": page},
                    "score": r.get("score", None),
                    "source": source_label,
                })
        except Exception:
            pass

    _pull(f"fw_{framework}",        f"fw_{framework}")
    _pull(f"assessment_{firm}",     f"assessment_{firm}")
    _pull(f"evidence_{firm}",       f"evidence_{firm}")

    seen = set()
    fresh, dups = [], []
    for r in pool:
        doc_id = r["metadata"]["doc_id"]
        page   = r["metadata"]["page"]
        head   = (r["text"][:120] or "").strip()
        key_all = (doc_id, page, head)
        if key_all in seen:
            continue
        seen.add(key_all)
        ((fresh if (doc_id, page) not in used_ev else dups)).append(r)

    def _score(row):
        s = row.get("score")
        try: return float(s) if s is not None else -1e9
        except: return -1e9

    fresh.sort(key=_score, reverse=True)
    dups.sort(key=_score, reverse=True)

    out = fresh[:k]
    if len(out) < k:
        out += dups[:(k - len(out))]
    return out[:k]

def _render_section_llm(
    *,
    provider: str,
    model: Optional[str],
    framework: str,
    section_id: str,
    section_name: str,
    section_prompt: str,
    overarching_prompt: str,
    memory: RollingMemory,
    firm: str,
    scope: Optional[str],
) -> Dict[str, Any]:
    retrieval_query = f"{section_name}: {section_prompt}\nFirm: {firm}\nScope: {scope or 'full'}"
    chunks = _retrieve_chunks(
        framework=framework, firm=firm, query_text=retrieval_query,
        used_ev=memory.used_evidence, k=RETRIEVE_K
    )

    ev_lines: List[str] = []
    new_used: Set[Tuple[str,int]] = set()
    rag_debug: List[Dict[str, Any]] = []

    for c in chunks:
        meta   = c["metadata"]
        doc_id = meta["doc_id"]
        page   = meta["page"]
        text   = c["text"]
        score  = c.get("score")
        source = c.get("source")
        ev_lines.append(f"[{doc_id} p.{page}] {text[:800]}")
        new_used.add((doc_id, page))
        rag_debug.append({
            "doc_id": doc_id,
            "page": page,
            "score": float(score) if isinstance(score, (int, float)) else None,
            "preview": (text or "")[:400].replace("\n", " ").strip(),
            "source": source,
        })

    system = (
        f"You are generating the '{section_name}' section of a compliance report for '{firm}'. "
        f"Maintain coherence and avoid repeating earlier points.\n\n"
        f"Global Guidance:\n{(overarching_prompt or '').strip()}"
    )
    user = (
        f"Section directive:\n{section_prompt.strip()}\n\n"
        f"{memory.to_prompt_block()}\n\n"
        "Use the retrieved evidence to ground claims (quote minimally, synthesize conclusions):\n"
        + "\n---\n".join(ev_lines)
    )
    text = chat_complete(
        provider=provider, model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3, max_tokens=1100,
        response_format=None  # narrative text; no JSON required
    )
    return {"text": text, "used": new_used, "rag_debug": rag_debug, "section_id": section_id}

def generate_report_sections(
    *,
    provider: str,
    model: Optional[str],
    framework: str,
    firm: str,
    sections_ordered: List[Dict[str, Any]],
    overarching_prompt: str,
    scope: Optional[str],
    prompt_overrides: Dict[str, str],
    include_rag_debug: bool = False,
) -> tuple[Dict[str, str], Optional[Dict[str, List[Dict[str, Any]]]]]:
    memory = RollingMemory()
    out_text: Dict[str, str] = {}
    rag_debug_map: Dict[str, List[Dict[str, Any]]] = {}

    outline_msg = [
        {"role": "system", "content": "You are an audit report planner."},
        {"role": "user", "content": "Create a 1-level outline for the following sections in order:\n" +
                                    "\n".join(f"- {s['name']}" for s in sections_ordered)}
    ]
    outline = chat_complete(
        provider=provider, model=model,
        messages=outline_msg, temperature=0.2, max_tokens=250,
        response_format=None
    )
    memory.points = [ln.strip("- ").strip() for ln in outline.split("\n") if ln.strip()][:MEM_POINTS_LIMIT]

    for s in sections_ordered:
        sec_id = s["id"]
        sec_name = s["name"]
        sec_prompt = (prompt_overrides.get(s["id"]) or s.get("default_prompt") or "").strip()

        sec = _render_section_llm(
            provider=provider, model=model,
            framework=framework,
            section_id=sec_id, section_name=sec_name,
            section_prompt=sec_prompt, overarching_prompt=overarching_prompt,
            memory=memory, firm=firm, scope=scope,
        )
        text: str = sec["text"]
        out_text[sec_name] = text
        if include_rag_debug:
            rag_debug_map[sec_id] = sec["rag_debug"]

        summ = _summarize_text_for_memory(text, provider=provider, model=model)
        combined = (memory.narrative_summary + "\n" + (summ.get("narrative") or "")).strip()
        re_summ = _summarize_text_for_memory(combined, provider=provider, model=model)
        memory.narrative_summary = (re_summ.get("narrative") or "")[:MEM_SUMMARY_TOKENS * 6]
        memory.points = list(dict.fromkeys(memory.points + (summ.get("bullets") or [])))[:MEM_POINTS_LIMIT]
        memory.used_evidence |= set(sec["used"])

    return out_text, (rag_debug_map if include_rag_debug else None)

def run_report(
    framework: str,
    firm: str,
    scope: Optional[str],
    *,
    provider: str,
    model: Optional[str],
    selected_sections: List[Dict[str, Any]],
    prompt_overrides: Dict[str, str],
    overarching_prompt: str,
    include_rag_debug: bool = False,
) -> Dict[str, Any]:
    assessor_cls = get_assessor(framework)
    assessor: BaseFrameworkAssessor = assessor_cls()

    findings = assessor.build_findings(BuildContext(firm=firm, scope=scope))

    sections_text, rag_debug = generate_report_sections(
        provider=provider, model=model,
        framework=framework, firm=firm,
        sections_ordered=selected_sections,
        overarching_prompt=overarching_prompt or "",
        scope=scope, prompt_overrides=prompt_overrides or {},
        include_rag_debug=include_rag_debug,
    )

    run_id = f"{framework}-{firm}-{os.getpid()}-{abs(hash((framework, firm)))%10**9}"
    out: Dict[str, Any] = {
        "run_id": run_id,
        "framework": framework,
        "firm": firm,
        "selected_sections": [s["name"] for s in selected_sections],
        "sections": sections_text,
        "findings": findings,
    }
    if include_rag_debug and rag_debug:
        out["rag_debug"] = rag_debug

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out

def load_run(run_id: str) -> Dict[str, Any]:
    p = RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    return json.loads(p.read_text(encoding="utf-8"))
