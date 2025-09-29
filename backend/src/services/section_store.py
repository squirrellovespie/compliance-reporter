from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict
from models.sections import Section

ROOT = Path(__file__).resolve().parents[1]  # .../backend/src
BASE = ROOT / "data" / "config" / "sections"
BASE.mkdir(parents=True, exist_ok=True)

def _path(framework: str) -> Path:
    return BASE / f"{framework}.json"

def load_sections(framework: str) -> List[Section]:
    p = _path(framework)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [Section(**s) for s in raw]

def save_sections(framework: str, sections: List[Section]) -> None:
    sections_sorted = sorted(sections, key=lambda s: s.position)
    payload = [s.model_dump() for s in sections_sorted]
    _path(framework).write_text(json.dumps(payload, indent=2), encoding="utf-8")

def delete_section(framework: str, section_id: str) -> None:
    cur = load_sections(framework)
    nxt = [s for s in cur if s.id != section_id]
    save_sections(framework, nxt)

def upsert_sections(framework: str, incoming: List[Section]) -> List[Section]:
    cur: Dict[str, Section] = {s.id: s for s in load_sections(framework)}
    for s in incoming:
        cur[s.id] = s
    merged = list(cur.values())
    # enforce unique positions
    positions = [s.position for s in merged]
    if len(set(positions)) != len(positions):
        raise ValueError("position conflict after upsert")
    save_sections(framework, merged)
    return load_sections(framework)
