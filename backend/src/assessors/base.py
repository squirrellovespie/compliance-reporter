from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import json

# vector search wrapper you already have
from services.vector_langchain import query as vs_query


@dataclass
class BuildContext:
    firm: str
    scope: Optional[str] = None


class BaseFrameworkAssessor:
    """
    Base class that:
      * loads a taxonomy (controls + micro_requirements)
      * provides a default build_findings that uses RAG over:
          - fw_<framework>
          - assessment_<firm>
          - evidence_<firm>

    Subclasses must set:
      * name: str               (framework slug, e.g., "seal" or "seal_test")
      * taxonomy_path(): Path   (where to load taxonomy YAML/JSON)
    """

    name: str = "base"

    # --------- taxonomy ---------
    def taxonomy_path(self) -> Path:
        """Subclasses should override."""
        raise NotImplementedError

    def _load_taxonomy(self) -> Dict[str, Any]:
        p = self.taxonomy_path()
        if not p.exists():
            raise FileNotFoundError(f"taxonomy not found: {p}")

        if p.suffix.lower() in (".yaml", ".yml"):
            import yaml
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

        return json.loads(p.read_text(encoding="utf-8")) or {}

    def _iter_controls(self) -> Iterable[Dict[str, Any]]:
        tax = getattr(self, "_taxonomy", None)
        if tax is None:
            tax = self._load_taxonomy()
            self._taxonomy = tax

        items = tax.get("controls") or tax.get("requirements") or []
        for ctrl in items:
            ctrl_id = (ctrl.get("id") or "").strip()
            ctrl_name = (ctrl.get("name") or "").strip()

            mrs = ctrl.get("micro_requirements") or []
            for mr in mrs:
                mr_id = (mr.get("id") or "").strip()
                prompt = (mr.get("prompt") or "").strip()
                synonyms = mr.get("synonyms") or []

                if not ctrl_id or not mr_id or not prompt:
                    # skip malformed entries (keeps findings stable)
                    continue

                yield {
                    "control_id": ctrl_id,
                    "control_name": ctrl_name,
                    "mr_id": mr_id,
                    "prompt": prompt,
                    "synonyms": synonyms,
                }

    # --------- vector helpers ---------
    @staticmethod
    def _col_fw(framework: str) -> str:
        return f"fw_{framework}"

    @staticmethod
    def _col_assessment(firm: str) -> str:
        return f"assessment_{firm}"

    @staticmethod
    def _col_evidence(firm: str) -> str:
        return f"evidence_{firm}"

    def _search(
        self,
        collection: str,
        text: str,
        k: int = 4,
        *,
        strategy: Optional[str] = None,  # "cosine" | "mmr" | "hybrid"
    ) -> List[Dict[str, Any]]:
        """
        Back/forward compatible with both vector_langchain.query signatures:
          - query(collection, text, k)
          - query(collection_name=..., text=..., k=..., strategy=...)
        """
        try:
            try:
                # Newer signature
                return vs_query(
                    collection_name=collection,
                    text=text,
                    k=k,
                    strategy=strategy,
                ) or []
            except TypeError:
                # Older signature
                return vs_query(collection, text, k) or []
        except Exception:
            return []

    # --------- core RAG logic ---------
    def build_findings(self, ctx: BuildContext) -> List[Dict[str, Any]]:
        """
        Simple heuristic:
          - for each micro-requirement, search assessment+evidence
          - if any hit is found, mark as "Meets" with medium confidence
        """
        fw_col = self._col_fw(self.name)
        assess_col = self._col_assessment(ctx.firm)
        evid_col = self._col_evidence(ctx.firm)

        findings: List[Dict[str, Any]] = []
        for item in self._iter_controls():
            q = item["prompt"]
            syn = item.get("synonyms") or []
            if syn:
                # keep query compact but helpful
                q += " | " + " | ".join(str(s) for s in syn if s)

            hits_fw = self._search(fw_col, q, k=3)
            hits_assess = self._search(assess_col, q, k=4)
            hits_evid = self._search(evid_col, q, k=6)

            ev_links: List[Dict[str, Any]] = []
            for h in (hits_assess + hits_evid):
                md = h.get("metadata") or {}
                ev_links.append({
                    "doc_id": md.get("doc_id") or md.get("source_pdf") or md.get("file") or "",
                    "page": md.get("page"),
                    "snippet": (h.get("text") or "")[:160],
                })

            assessment = "Meets" if ev_links else "Unknown"
            confidence = 0.75 if ev_links else 0.2

            findings.append({
                "id": f"{item['control_id']}.{item['mr_id']}",
                "control_id": item["control_id"],
                "control_name": item["control_name"],
                "micro_requirement_id": item["mr_id"],
                "claim": item["prompt"],
                "assessment": assessment,
                "confidence": confidence,
                "framework_refs": [f"[{self.name}] control {item['control_id']}"] + (
                    ["[guideline context present]"] if hits_fw else []
                ),
                "rationale": (
                    "Evidence retrieved that aligns with the control intent."
                    if ev_links else
                    "No clear evidence retrieved."
                ),
                "evidence_links": ev_links[:6],
            })

        return findings

    # --------- deterministic fallback (optional) ---------
    # Orchestrator does the narrative now; keep this for debugging / old callers.
    def render_section_text(
        self,
        section_id: str,
        section_name: str,
        prompt: str,
        firm: str,
        scope: Optional[str],
        findings: List[Dict[str, Any]],
    ) -> str:
        return self._fallback_narrative(section_name, firm, scope, findings, prompt)

    def _fallback_narrative(
        self,
        section_name: str,
        firm: str,
        scope: Optional[str],
        findings: List[Dict[str, Any]],
        prompt: str,
    ) -> str:
        lines: List[str] = []
        lines.append(f"{section_name} for {firm}{' — ' + scope if scope else ''}.")
        lines.append(prompt if prompt else "This section summarizes the current posture and evidence.")

        meets = [f for f in findings if (f.get("assessment") or "").lower() == "meets"]
        unknown = [f for f in findings if (f.get("assessment") or "").lower() != "meets"]

        if meets:
            lines.append(f"{len(meets)} requirement(s) appear to be met based on uploaded evidence.")
        if unknown:
            lines.append(f"{len(unknown)} requirement(s) lack clear evidence and may require follow-up.")

        return "\n\n".join(lines)