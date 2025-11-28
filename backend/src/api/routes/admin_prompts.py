from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Optional
from pathlib import Path
import yaml, os, tempfile

router = APIRouter(prefix="/admin/prompts", tags=["admin-prompts"])

GUIDELINES_DIR = Path(__file__).resolve().parents[2] / "guidelines"
GUIDELINES_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class SectionUpsert(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    position: int = Field(..., ge=0)
    default_prompt: str = ""
    enabled: bool = True

    @validator("id")
    def _safe_id(cls, v: str) -> str:
        if not all(c.isalnum() or c in ("_", "-") for c in v):
            raise ValueError("id must be alphanumeric with '_' or '-' only")
        return v

class SectionPatch(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = Field(None, ge=0)
    default_prompt: Optional[str] = None
    enabled: Optional[bool] = None

class ReorderRequest(BaseModel):
    positions: List[Dict[str, int]]

class OverarchingPatch(BaseModel):
    overarching: str

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _prompts_path(framework: str) -> Path:
    p = GUIDELINES_DIR / framework / "prompts.yaml"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"prompts.yaml not found for framework '{framework}'")
    return p

def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid YAML: {e}")
    data.setdefault("overarching", "")
    data.setdefault("sections", [])
    for s in data["sections"]:
        s.setdefault("enabled", True)
    return data

def _atomic_write(path: Path, data: Dict[str, Any]):
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".prompts.", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)
        os.replace(tmp_name, path)  # atomic write
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

def _find_section(data: Dict[str, Any], section_id: str) -> Optional[Dict[str, Any]]:
    for s in data.get("sections", []):
        if s.get("id") == section_id:
            return s
    return None

def _resort_by_position(data: Dict[str, Any]):
    data["sections"] = sorted(data.get("sections", []), key=lambda s: int(s.get("position", 0)))

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@router.get("/{framework}")
def get_prompts(framework: str):
    """Return the entire prompts.yaml contents."""
    path = _prompts_path(framework)
    return _load_yaml(path)

@router.get("/{framework}/sections")
def list_sections(framework: str):
    """Return only the sections list."""
    data = _load_yaml(_prompts_path(framework))
    return {"sections": data.get("sections", [])}

@router.patch("/{framework}/overarching")
def update_overarching(framework: str, body: OverarchingPatch):
    """Update the overarching prompt."""
    path = _prompts_path(framework)
    data = _load_yaml(path)
    data["overarching"] = (body.overarching or "").strip()
    _atomic_write(path, data)
    return {"status": "ok", "updated": "overarching"}

@router.post("/{framework}/sections")
def add_section(framework: str, body: SectionUpsert):
    """Add a new section (id must be unique)."""
    path = _prompts_path(framework)
    data = _load_yaml(path)
    if any(s.get("id") == body.id for s in data["sections"]):
        raise HTTPException(status_code=400, detail=f"Section '{body.id}' already exists")

    new_section = body.dict()
    data["sections"].append(new_section)
    _resort_by_position(data)
    _atomic_write(path, data)
    return {"status": "ok", "created": body.id, "section": new_section}

@router.patch("/{framework}/sections/{section_id}")
def update_section(framework: str, section_id: str, body: SectionPatch):
    """Edit section name, position, prompt, or enabled flag."""
    path = _prompts_path(framework)
    data = _load_yaml(path)
    section = _find_section(data, section_id)
    if not section:
        raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")

    updates = body.dict(exclude_unset=True)
    section.update({k: v for k, v in updates.items() if v is not None})
    _resort_by_position(data)
    _atomic_write(path, data)
    return {"status": "ok", "updated": section_id, "section": section}

@router.patch("/{framework}/sections/reorder")
def reorder_sections(framework: str, req: ReorderRequest):
    """Bulk reorder section positions."""
    path = _prompts_path(framework)
    data = _load_yaml(path)
    id_map = {s["id"]: s for s in data["sections"]}
    for item in req.positions:
        sid, pos = item.get("id"), item.get("position")
        if sid not in id_map:
            raise HTTPException(status_code=404, detail=f"Section '{sid}' not found")
        id_map[sid]["position"] = pos
    _resort_by_position(data)
    _atomic_write(path, data)
    return {"status": "ok", "reordered": [s["id"] for s in data["sections"]]}

@router.patch("/{framework}/sections/{section_id}/enabled")
def set_section_enabled(framework: str, section_id: str, body: Dict[str, bool]):
    """Toggle whether a section is active (enabled)."""
    path = _prompts_path(framework)
    data = _load_yaml(path)
    section = _find_section(data, section_id)
    if not section:
        raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")

    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="Missing boolean field 'enabled'")
    section["enabled"] = enabled
    _atomic_write(path, data)
    return {"status": "ok", "section": section_id, "enabled": enabled}

@router.delete("/{framework}/sections/{section_id}")
def delete_section(framework: str, section_id: str):
    """Delete a section by ID."""
    path = _prompts_path(framework)
    data = _load_yaml(path)
    before = len(data["sections"])
    data["sections"] = [s for s in data["sections"] if s.get("id") != section_id]
    if len(data["sections"]) == before:
        raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")
    _atomic_write(path, data)
    return {"status": "ok", "deleted": section_id, "remaining": len(data["sections"])}

@router.put("/{framework}")
def replace_prompts(framework: str, body: Dict[str, Any]):
    """Replace the entire prompts.yaml with new content."""
    if "overarching" not in body or "sections" not in body:
        raise HTTPException(status_code=400, detail="Body must contain 'overarching' and 'sections'")
    path = _prompts_path(framework)
    _atomic_write(path, body)
    return {"status": "ok", "replaced": path.name}
