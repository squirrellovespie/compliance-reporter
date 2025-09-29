from __future__ import annotations
from typing import Dict, Any, List, Tuple
from services.vector_langchain import query as q

def search_dual(plan: dict) -> tuple[list[dict], list[dict]]:
    text = plan.get("prompt","").strip() + " " + " ".join(plan.get("synonyms", []))
    fw_hits = q(f"fw:{plan['framework']}", text, k=6)
    fw_struct = [{
        "framework": plan["framework"],
        "control_id": plan["control_id"],
        "text": h["text"],
        "source_pdf": h["metadata"].get("source_pdf"),
        "page": h["metadata"].get("page"),
        "clause_id": None,
        "id": h.get("id") or (h["metadata"] or {}).get("id"),
    } for h in fw_hits]

    ev_struct: list[dict] = []
    firm = (plan.get("firm") or "").strip()
    if firm:
        ev_hits = q(f"ev:{firm}", text, k=10)
        # Prefer assessment, then higher score
        ev_hits.sort(key=lambda h: (
            0 if (h["metadata"] or {}).get("type") == "assessment" else 1,
            -(h.get("score") or 0)
        ))
        ev_struct = [{
            "doc_id": (h["metadata"] or {}).get("doc_id") or h.get("id"),
            "page": (h["metadata"] or {}).get("page"),
            "text": h["text"],
            "type": (h["metadata"] or {}).get("type"),
            "id": h.get("id") or (h["metadata"] or {}).get("id"),
        } for h in ev_hits]
    return fw_struct, ev_struct
