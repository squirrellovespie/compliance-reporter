from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

SECTIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "sections"
SECTIONS_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class SectionDef:
    id: str
    name: str
    position: int
    prompt: str

# Generic defaults you can reuse (will be used if no file found)
DEFAULT_SECTIONS: Dict[str, List[SectionDef]] = {
    "_generic": [
        SectionDef("exec_summary", "Executive Summary", 1, "Write a concise executive summary tailored to the client and scope."),
        SectionDef("governance", "Governance and Risk Management", 2, "Summarize governance, leadership accountability, risk appetite, and oversight."),
        SectionDef("tech_ops", "Technology Operations and Resilience", 3, "Summarize IT operations, change/patch, asset, continuity, DR/BCP posture."),
        SectionDef("cyber", "Cyber Security", 4, "Summarize threat detection, defense controls, data protection, and monitoring."),
        SectionDef("third_party", "Third-Party and Outsourcing Oversight", 5, "Summarize third-party risk management and contractual controls."),
        SectionDef("maturity", "Maturity Assessment and Gap Summary", 6, "Provide maturity scores, key gaps, and benchmark context."),
        SectionDef("recs", "Recommendations", 7, "Prioritized recommendations with effort/impact and timeline."),
        SectionDef("conclusion", "Conclusion", 8, "Close with overall compliance posture and next steps."),
    ]
}

def _file(framework: str) -> Path:
    return SECTIONS_DIR / f"{framework}.json"

def load_sections(framework: str) -> List[SectionDef]:
    p = _file(framework)
    if not p.exists():
        # not found -> fall back to generic
        return list(DEFAULT_SECTIONS["_generic"])
    data = json.loads(p.read_text(encoding="utf-8")) or []
    out: List[SectionDef] = []
    for row in data:
        out.append(
            SectionDef(
                id=row["id"],
                name=row["name"],
                position=int(row.get("position", 0)),
                prompt=row.get("prompt", ""),
            )
        )
    out.sort(key=lambda s: s.position)
    return out

def save_sections(framework: str, sections: List[SectionDef]) -> None:
    sections = sorted(sections, key=lambda s: s.position)
    payload = [asdict(s) for s in sections]
    _file(framework).write_text(json.dumps(payload, indent=2), encoding="utf-8")

def upsert_sections(framework: str, new_sections: List[Dict]) -> List[SectionDef]:
    existing = {s.id: s for s in load_sections(framework)}
    for row in new_sections:
        sid = row["id"]
        existing[sid] = SectionDef(
            id=sid,
            name=row["name"],
            position=int(row["position"]),
            prompt=row.get("prompt", ""),
        )
    out = list(existing.values())
    save_sections(framework, out)
    return out

def delete_section(framework: str, section_id: str) -> List[SectionDef]:
    cur = [s for s in load_sections(framework) if s.id != section_id]
    save_sections(framework, cur)
    return cur

def seed_defaults(framework: str) -> List[SectionDef]:
    """Write generic defaults as the framework's file (idempotent)."""
    if _file(framework).exists():
        return load_sections(framework)
    base = list(DEFAULT_SECTIONS["_generic"])
    save_sections(framework, base)
    return base
