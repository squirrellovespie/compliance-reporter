from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

def _root() -> Path:
    # .../backend/src
    return Path(__file__).resolve().parents[1]

def _prompts_path(framework: str) -> Path:
    return _root() / "guidelines" / framework / "prompts.yaml"

def load_prompts(framework: str) -> Dict[str, Any]:
    """
    Structure:
    {
      "overarching": str,
      "sections": [
         {id, name, position, default_prompt}
      ]
    }
    """
    p = _prompts_path(framework)
    if not p.exists():
        # graceful default
        return {"overarching": "", "sections": []}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data.setdefault("overarching", "")
    data.setdefault("sections", [])
    # Normalize section fields
    for s in data["sections"]:
        s.setdefault("id", s.get("name", "").lower().replace(" ", "_"))
        s.setdefault("position", 0)
        s.setdefault("default_prompt", f"Write the '{s.get('name','Section')}' section.")
    # Sort by position for convenience
    data["sections"] = sorted(data["sections"], key=lambda x: x.get("position", 0))
    return data

def get_overarching(framework: str) -> str:
    return load_prompts(framework).get("overarching","")

def get_sections(framework: str) -> List[Dict[str, Any]]:
    return load_prompts(framework).get("sections", [])
