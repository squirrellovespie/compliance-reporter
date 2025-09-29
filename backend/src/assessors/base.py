from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import os
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
      * provides a default render_section_text with LLM fallback
    Subclasses must set:
      * name: str               (framework key, e.g., "seal")
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
        if p.suffix.lower() in [".yaml", ".yml"]:
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
            # expect micro_requirements array
            mrs = ctrl.get("micro_requirements") or []
            for mr in mrs:
                yield {
                    "control_id": ctrl.get("id"),
                    "control_name": ctrl.get("name", ""),
                    "mr_id": mr.get("id"),
                    "prompt": mr.get("prompt", ""),
                    "synonyms": mr.get("synonyms", []),
                }

    # --------- vector helpers ---------
    @staticmethod
    def _col_fw(framework: str) -> str:
        # Chroma name rules (no colon): use fw_<framework>
        return f"fw_{framework}"

    @staticmethod
    def _col_assessment(firm: str) -> str:
        return f"assessment_{firm}"

    @staticmethod
    def _col_evidence(firm: str) -> str:
        return f"evidence_{firm}"

    def _search(self, collection: str, text: str, k: int = 4) -> List[Dict[str, Any]]:
        try:
            return vs_query(collection, text, k)
        except Exception:
            return []

    # --------- core RAG logic ---------
    def build_findings(self, ctx: BuildContext) -> List[Dict[str, Any]]:
        """
        Very simple heuristic:
          - for each micro-requirement, search assessment+evidence
          - if any decent hit is found, mark as "Meets" with medium confidence
        """
        fw_col = self._col_fw(self.name)
        assess_col = self._col_assessment(ctx.firm)
        evid_col = self._col_evidence(ctx.firm)

        findings: List[Dict[str, Any]] = []
        for item in self._iter_controls():
            q = item["prompt"]
            if item.get("synonyms"):
                q += " | " + " | ".join(item["synonyms"])

            hits_fw = self._search(fw_col, q, k=3)
            hits_assess = self._search(assess_col, q, k=4)
            hits_evid = self._search(evid_col, q, k=6)

            ev_links = []
            for h in (hits_assess + hits_evid):
                md = h.get("metadata") or {}
                ev_links.append({
                    "doc_id": md.get("doc_id") or md.get("source_pdf") or md.get("file", ""),
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
                "rationale": "Evidence retrieved that aligns with the control intent." if ev_links else
                             "No clear evidence retrieved.",
                "evidence_links": ev_links[:6],
            })

        return findings

    # --------- narrative renderer (LLM optional) ---------
    def render_section_text(
        self,
        section_id: str,
        section_name: str,
        prompt: str,
        firm: str,
        scope: Optional[str],
        findings: List[Dict[str, Any]],
    ) -> str:
        """
        If OPENAI_API_KEY is set, call the LLM to produce narrative text.
        Otherwise, produce a structured fallback using available findings.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                # Construct compact context
                brief = []
                for f in findings[:20]:
                    brief.append(f"- {f['id']}: {f['assessment']} (conf {int(f['confidence']*100)}%) :: {f['claim']}")
                ctx = "\n".join(brief)
                sys = (
                    "You are an expert compliance report writer. "
                    "Write a clear, concise narrative for the section using the prompt, "
                    "the firm's context, and the summarized findings. Do not output markdown symbols."
                )
                user = (
                    f"Firm: {firm}\nScope: {scope or 'n/a'}\n"
                    f"Section: {section_name}\nPrompt: {prompt}\n\n"
                    f"Findings (summary):\n{ctx}\n\n"
                    f"Write 2-5 short paragraphs. Use professional tone. No bullet symbols."
                )
                resp = client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[{"role":"system","content":sys},{"role":"user","content":user}],
                    temperature=0.3,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:
                # fall through to deterministic fallback
                return self._fallback_narrative(section_name, firm, scope, findings, prompt, error=str(e))
        else:
            return self._fallback_narrative(section_name, firm, scope, findings, prompt)

    def _fallback_narrative(
        self,
        section_name: str,
        firm: str,
        scope: Optional[str],
        findings: List[Dict[str, Any]],
        prompt: str,
        error: Optional[str] = None,
    ) -> str:
        lines = []
        if error:
            lines.append(f"(LLM unavailable or failed: {error})")
        lines.append(f"{section_name} for {firm}{' — ' + scope if scope else ''}.")
        lines.append(prompt if prompt else "This section summarizes the current posture and evidence.")
        # Light synthesis
        meets = [f for f in findings if f["assessment"].lower() == "meets"]
        unknown = [f for f in findings if f["assessment"].lower() != "meets"]
        if meets:
            lines.append(f"{len(meets)} requirement(s) appear to be met based on uploaded evidence.")
        if unknown:
            lines.append(f"{len(unknown)} requirement(s) lack clear evidence and may require follow-up.")
        return "\n\n".join(lines)
