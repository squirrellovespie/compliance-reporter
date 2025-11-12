from __future__ import annotations
from fastapi import APIRouter, HTTPException
from typing import Any, Dict
from pathlib import Path
import yaml, os

router = APIRouter(prefix="/admin/prompts", tags=["admin-prompts"])

GUIDELINES_DIR = Path(__file__).resolve().parents[2] / "guidelines"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _prompts_path(framework: str) -> Path:
    p = GUIDELINES_DIR / framework / "prompts.yaml"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"prompts.yaml not found for framework '{framework}'")
    return p

def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid YAML file: {e}")

def _save_yaml(path: Path, data: Dict[str, Any]):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)

# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@router.get("/{framework}")
def get_prompts(framework: str):
    """Return the entire prompts.yaml contents."""
    path = _prompts_path(framework)
    return _load_yaml(path)

@router.patch("/{framework}/overarching")
def update_overarching(framework: str, body: Dict[str, str]):
    """Update just the overarching prompt."""
    path = _prompts_path(framework)
    data = _load_yaml(path)

    new_text = body.get("overarching")
    if not isinstance(new_text, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'overarching' field")

    data["overarching"] = new_text.strip()
    _save_yaml(path, data)
    return {"status": "ok", "updated": "overarching"}

@router.patch("/{framework}/sections/{section_id}")
def update_section(framework: str, section_id: str, body: Dict[str, Any]):
    """
    Edit one section (name, position, default_prompt, etc.)
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)

    sections = data.get("sections", [])
    for s in sections:
        if s.get("id") == section_id:
            s.update(body)
            _save_yaml(path, data)
            return {"status": "ok", "updated": section_id}

    raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")

@router.put("/{framework}")
def replace_prompts(framework: str, body: Dict[str, Any]):
    """
    Replace entire prompts.yaml structure.
    Body must contain keys: overarching (str), sections (list)
    """
    if "overarching" not in body or "sections" not in body:
        raise HTTPException(status_code=400, detail="Body must contain 'overarching' and 'sections'")
    path = _prompts_path(framework)
    _save_yaml(path, body)
    return {"status": "ok", "replaced": path.name}

@router.delete("/{framework}/sections/{section_id}")
def delete_section(framework: str, section_id: str):
    """Remove one section from prompts.yaml."""
    path = _prompts_path(framework)
    data = _load_yaml(path)

    before = len(data.get("sections", []))
    data["sections"] = [s for s in data.get("sections", []) if s.get("id") != section_id]
    after = len(data["sections"])

    if before == after:
        raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")

    _save_yaml(path, data)
    return {"status": "ok", "deleted": section_id, "remaining": after}
