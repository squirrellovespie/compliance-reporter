# backend/src/engine/orchestrator.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set, Iterable
from pathlib import Path
import os, json

from assessors.registry import get_assessor
from assessors.base import BuildContext, BaseFrameworkAssessor

from services.ai_client import chat_complete
from services.vector_langchain import query as vs_query

# Persistent runs directory (for JSON + PDFs)
RUNS_DIR = Path(os.getenv("RUNS_PATH", "./src/data/runs")).resolve()
RUNS_DIR.mkdir(parents=True, exist_ok=True)

# ---- Rolling context knobs ----
MEM_SUMMARY_TOKENS = 350       # target length of rolling narrative memory
MEM_POINTS_LIMIT   = 12        # max bullets carried forward
RETRIEVE_K         = 8         # top-k RAG chunks per section


# ---------- Rolling Memory ----------
@dataclass
class RollingMemory:
    narrative_summary: str = ""                           # compact narrative so far
    points: List[str] = field(default_factory=list)       # bullets so far
    used_evidence: Set[Tuple[str, int]] = field(default_factory=set)  # (doc_id, page)

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


# ---------- helpers ----------
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
        {"role": "user", "content": prompt + "\n\n---\n" + (text or "").strip()},
    ]
    resp = chat_complete(
        provider=provider, model=model,
        messages=messages,
        # OpenAI can use native JSON mode; xAI currently cannot
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
    *,
    k: int = RETRIEVE_K,
    retrieval_strategy: Optional[str] = None,  # "cosine" | "mmr" | "hybrid"
) -> List[Dict[str, Any]]:
    """
    Retrieve top-k across multiple collections:
      - fw_<framework>      (guidelines)
      - assessment_<firm>   (firm assessment)
      - evidence_<firm>     (supporting evidence)
    Prefer chunks not yet used (by (doc_id,page)), then fill with dupes if needed.
    Returns rows with normalized fields: text, metadata{doc_id,page}, score, source.
    """
    pool: List[Dict[str, Any]] = []

    def _pull(collection: str, source_label: str):
        try:
            # Ask for more than needed from each pool; we’ll merge -> dedupe -> trim
            try:
                rows = vs_query(
                    collection_name=collection,
                    text=query_text,
                    k=k*2,
                    strategy=retrieval_strategy,
                ) or []
            except TypeError:
                # Back-compat with older signature (no strategy)
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
            # collection may not exist yet; ignore
            pass

    _pull(f"fw_{framework}",        f"fw_{framework}")
    _pull(f"assessment_{firm}",     f"assessment_{firm}")
    _pull(f"evidence_{firm}",       f"evidence_{firm}")

    # De-duplicate by (doc_id, page, text_head) and split into fresh vs already used
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

        key_used = (doc_id, page)
        (fresh if key_used not in used_ev else dups).append(r)

    # Sort each bucket by descending score if available
    def _score(row):
        s = row.get("score")
        try:
            return float(s) if s is not None else -1e9
        except Exception:
            return -1e9

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
    retrieval_strategy: Optional[str],
) -> Dict[str, Any]:
    """
    Produce one section text using:
    - Overarching prompt
    - Rolling memory (prior narrative + bullets + used evidence)
    - Fresh RAG chunks (with dedupe against used evidence)
    Also returns 'rag_debug' list for UI inspection.
    """
    retrieval_query = f"{section_name}: {section_prompt}\nFirm: {firm}\nScope: {scope or 'full'}"
    chunks = _retrieve_chunks(
        framework=framework,
        firm=firm,
        query_text=retrieval_query,
        used_ev=memory.used_evidence,
        k=RETRIEVE_K,
        retrieval_strategy=retrieval_strategy,
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
            "source": source,  # tells you fw_ / assessment_ / evidence_
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
    return {
        "text": text,
        "used": new_used,
        "rag_debug": rag_debug,
        "section_id": section_id,
        "section_name": section_name,
    }


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
    retrieval_strategy: Optional[str] = None,
) -> tuple[Dict[str, str], Optional[Dict[str, List[Dict[str, Any]]]]]:
    """
    Generate all section texts with rolling memory.
    Returns: (sections_text, rag_debug_map_or_None)
    """
    memory = RollingMemory()
    out_text: Dict[str, str] = {}
    rag_debug_map: Dict[str, List[Dict[str, Any]]] = {}

    # Small outline → better global coherence
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

    # Generate each section in order
    for s in sections_ordered:
        sec_id = s["id"]
        sec_name = s["name"]
        sec_prompt = (prompt_overrides.get(s["id"]) or s.get("default_prompt") or "").strip()

        sec = _render_section_llm(
            provider=provider, model=model,
            framework=framework,
            section_id=sec_id,
            section_name=sec_name,
            section_prompt=sec_prompt,
            overarching_prompt=overarching_prompt,
            memory=memory,
            firm=firm,
            scope=scope,
            retrieval_strategy=retrieval_strategy,
        )
        text: str = sec["text"]
        out_text[sec_name] = text

        if include_rag_debug:
            rag_debug_map[sec_id] = sec["rag_debug"]

        # Update rolling memory
        summ = _summarize_text_for_memory(text, provider=provider, model=model)
        combined = (memory.narrative_summary + "\n" + (summ.get("narrative") or "")).strip()
        re_summ = _summarize_text_for_memory(combined, provider=provider, model=model)
        memory.narrative_summary = (re_summ.get("narrative") or "")[:MEM_SUMMARY_TOKENS * 6]
        memory.points = list(dict.fromkeys(memory.points + (summ.get("bullets") or [])))[:MEM_POINTS_LIMIT]
        memory.used_evidence |= set(sec["used"])

    return out_text, (rag_debug_map if include_rag_debug else None)


# ---------- public APIs ----------
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
    retrieval_strategy: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronous report generation (non-streaming).
    Persists the run JSON and returns the result payload.
    """
    assessor_cls = get_assessor(framework)
    assessor: BaseFrameworkAssessor = assessor_cls()

    findings = assessor.build_findings(BuildContext(firm=firm, scope=scope))

    sections_text, rag_debug = generate_report_sections(
        provider=provider, model=model,
        framework=framework,
        firm=firm,
        sections_ordered=selected_sections,
        overarching_prompt=overarching_prompt or "",
        scope=scope,
        prompt_overrides=prompt_overrides or {},
        include_rag_debug=include_rag_debug,
        retrieval_strategy=retrieval_strategy,
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


def run_report_stream(
    *,
    framework: str,
    firm: str,
    scope: Optional[str],
    selected_sections: List[Dict[str, Any]],
    prompt_overrides: Dict[str, str],
    overarching_prompt: str,
    include_rag_debug: bool,
    provider: str,
    model: Optional[str],
    retrieval_strategy: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Iterable[str]:
    """
    NDJSON streamer. Yields JSON lines as text events:

      {"event":"start","run_id":...}
      {"event":"section_start","section_id":...,"section_name":...}
      {"event":"section_text","section_id":...,"section_name":...,"text":...}
      {"event":"end","run_id":...,"ok":true}

    Persists the final run JSON (same format as non-streaming).

    If run_id is provided, it is used for all events and the saved file;
    otherwise a new one is generated.
    """
    assessor_cls = get_assessor(framework)
    assessor: BaseFrameworkAssessor = assessor_cls()
    findings = assessor.build_findings(BuildContext(firm=firm, scope=scope))

    # Use incoming run_id (webhook mode) or generate one (normal streaming mode)
    if run_id is None:
        run_id = f"{framework}-{firm}-{os.getpid()}-{abs(hash((framework, firm)))%10**9}"

    yield json.dumps({"event": "start", "run_id": run_id, "framework": framework, "firm": firm}) + "\n"

    # Rolling memory + outline
    memory = RollingMemory()
    outline_msg = [
        {"role": "system", "content": "You are an audit report planner."},
        {"role": "user", "content": "Create a 1-level outline for the following sections in order:\n" +
                                    "\n".join(f"- {s['name']}" for s in selected_sections)}
    ]
    outline = chat_complete(provider=provider, model=model, messages=outline_msg, temperature=0.2, max_tokens=250)
    memory.points = [ln.strip("- ").strip() for ln in outline.split("\n") if ln.strip()][:MEM_POINTS_LIMIT]

    sections_text: Dict[str, str] = {}
    rag_debug_map: Dict[str, List[Dict[str, Any]]] = {}

    for s in selected_sections:
        sec_id = s["id"]
        sec_name = s["name"]
        sec_prompt = (prompt_overrides.get(s["id"]) or s.get("default_prompt") or "").strip()

        yield json.dumps({
            "event": "section_start",
            "run_id": run_id,
            "section_id": sec_id,
            "section_name": sec_name,
        }) + "\n"

        sec = _render_section_llm(
            provider=provider, model=model,
            framework=framework,
            section_id=sec_id,
            section_name=sec_name,
            section_prompt=sec_prompt,
            overarching_prompt=overarching_prompt,
            memory=memory,
            firm=firm,
            scope=scope,
            retrieval_strategy=retrieval_strategy,
        )

        text: str = sec["text"]
        sections_text[sec_name] = text
        if include_rag_debug:
            rag_debug_map[sec_id] = sec["rag_debug"]

        # Stream the completed section body
        yield json.dumps({
            "event": "section_text",
            "run_id": run_id,
            "section_id": sec_id,
            "section_name": sec_name,
            "text": text,
        }) + "\n"

        # Update rolling memory
        summ = _summarize_text_for_memory(text, provider=provider, model=model)
        combined = (memory.narrative_summary + "\n" + (summ.get("narrative") or "")).strip()
        re_summ = _summarize_text_for_memory(combined, provider=provider, model=model)
        memory.narrative_summary = (re_summ.get("narrative") or "")[:MEM_SUMMARY_TOKENS * 6]
        memory.points = list(dict.fromkeys(memory.points + (summ.get("bullets") or [])))[:MEM_POINTS_LIMIT]
        memory.used_evidence |= set(sec["used"])

    # Persist final artifact
    out: Dict[str, Any] = {
        "run_id": run_id,
        "framework": framework,
        "firm": firm,
        "selected_sections": [s["name"] for s in selected_sections],
        "sections": sections_text,
        "findings": findings,
    }
    if include_rag_debug and rag_debug_map:
        out["rag_debug"] = rag_debug_map

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    yield json.dumps({"event": "end", "run_id": run_id, "ok": True}) + "\n"


def load_run(run_id: str) -> Dict[str, Any]:
    p = RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    return json.loads(p.read_text(encoding="utf-8"))
