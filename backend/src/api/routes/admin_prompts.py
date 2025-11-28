# backend/src/api/routes/admin_prompts.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List
from pathlib import Path
import yaml

router = APIRouter(prefix="/admin/prompts", tags=["admin-prompts"])

# guidelines dir: backend/src/guidelines/<framework>/prompts.yaml
GUIDELINES_DIR = Path(__file__).resolve().parents[2] / "guidelines"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _prompts_path(framework: str) -> Path:
    p = GUIDELINES_DIR / framework / "prompts.yaml"
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail=f"prompts.yaml not found for framework '{framework}'",
        )
    return p


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid YAML file: {e}")


def _save_yaml(path: Path, data: Dict[str, Any]):
    # No backups, just overwrite in place
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)


def _find_section(data: Dict[str, Any], section_id: str) -> Dict[str, Any]:
    sections: List[Dict[str, Any]] = data.get("sections", []) or []
    for s in sections:
        if s.get("id") == section_id:
            return s
    raise HTTPException(
        status_code=404,
        detail=f"Section '{section_id}' not found",
    )


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@router.get("/{framework}")
def get_prompts(framework: str):
    """
    Return the entire prompts.yaml contents as JSON.
    """
    path = _prompts_path(framework)
    return _load_yaml(path)


@router.get("/{framework}/sections")
def list_sections(framework: str):
    """
    Return just the sections list for a framework.
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)
    return {
        "framework": framework,
        "sections": data.get("sections", []) or [],
    }


@router.patch("/{framework}/overarching")
def update_overarching(framework: str, body: Dict[str, Any]):
    """
    Update just the overarching prompt text.
    Body: { "overarching": "<new text>" }
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)

    new_text = body.get("overarching")
    if not isinstance(new_text, str):
        raise HTTPException(
            status_code=400,
            detail="Missing or invalid 'overarching' field",
        )

    data["overarching"] = new_text.strip()
    _save_yaml(path, data)
    return {"status": "ok", "updated": "overarching"}


@router.post("/{framework}/sections")
def add_section(framework: str, body: Dict[str, Any]):
    """
    Append a new section to prompts.yaml.

    Expected body (example):
    {
      "id": "pilot_section",
      "name": "Pilot Section",
      "position": 99,
      "default_prompt": "Prompt text...",
      "enabled": true
    }
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)

    sid = body.get("id")
    name = body.get("name")
    position = body.get("position")

    if not isinstance(sid, str) or not sid.strip():
        raise HTTPException(status_code=400, detail="Missing or invalid 'id'")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="Missing or invalid 'name'")
    if not isinstance(position, int):
        raise HTTPException(status_code=400, detail="Missing or invalid 'position' (int required)")

    sections: List[Dict[str, Any]] = data.get("sections", []) or []

    # ensure no duplicate id
    if any(s.get("id") == sid for s in sections):
        raise HTTPException(
            status_code=400,
            detail=f"Section id '{sid}' already exists",
        )

    new_section = {
        "id": sid,
        "name": name,
        "position": position,
        "default_prompt": body.get("default_prompt", "") or "",
    }
    # optional flag to support enabling/disabling
    if "enabled" in body:
        new_section["enabled"] = bool(body["enabled"])

    sections.append(new_section)
    data["sections"] = sections

    _save_yaml(path, data)
    return {"status": "ok", "added": sid}


@router.patch("/{framework}/sections/reorder")
def reorder_sections(framework: str, body: Dict[str, Any]):
    """
    Bulk update 'position' across sections.

    Body:
    {
      "positions": [
        { "id": "exec_summary", "position": 1 },
        { "id": "governance", "position": 2 },
        ...
      ]
    }
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)

    positions = body.get("positions")
    if not isinstance(positions, list):
        raise HTTPException(
            status_code=400,
            detail="Body must contain 'positions': [ { 'id': str, 'position': int }, ... ]",
        )

    pos_map: Dict[str, int] = {}
    for item in positions:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        pos = item.get("position")
        if isinstance(sid, str) and isinstance(pos, int):
            pos_map[sid] = pos

    if not pos_map:
        raise HTTPException(
            status_code=400,
            detail="No valid 'id'/'position' pairs provided",
        )

    sections: List[Dict[str, Any]] = data.get("sections", []) or []
    updated_ids: List[str] = []

    for s in sections:
        sid = s.get("id")
        if sid in pos_map:
            s["position"] = pos_map[sid]
            updated_ids.append(sid)

    if not updated_ids:
        raise HTTPException(
            status_code=404,
            detail="No matching sections found for provided ids",
        )

    # Optional: keep YAML in position order
    sections.sort(key=lambda s: int(s.get("position", 0)))
    data["sections"] = sections

    _save_yaml(path, data)
    return {"status": "ok", "updated": updated_ids}


@router.patch("/{framework}/sections/{section_id}")
def update_section(framework: str, section_id: str, body: Dict[str, Any]):
    """
    Edit one section (name, position, default_prompt, enabled, etc.).

    Example body:
    {
      "name": "New Name",
      "position": 5,
      "default_prompt": "Updated prompt...",
      "enabled": false
    }

    Note: 'id' field in body is ignored (we don't allow changing the id here).
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)

    sections: List[Dict[str, Any]] = data.get("sections", []) or []

    # don't allow changing the id via patch
    body = dict(body)
    body.pop("id", None)

    for s in sections:
        if s.get("id") == section_id:
            # Validation for position if present
            if "position" in body and not isinstance(body["position"], int):
                raise HTTPException(
                    status_code=400,
                    detail="'position' must be an integer",
                )
            # simple update of allowed keys
            for k, v in body.items():
                if k in ("name", "position", "default_prompt", "enabled"):
                    s[k] = v
            _save_yaml(path, data)
            return {"status": "ok", "updated": section_id}

    raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")


@router.delete("/{framework}/sections/{section_id}")
def delete_section(framework: str, section_id: str):
    """
    Remove one section from prompts.yaml.
    """
    path = _prompts_path(framework)
    data = _load_yaml(path)

    sections: List[Dict[str, Any]] = data.get("sections", []) or []
    before = len(sections)
    sections = [s for s in sections if s.get("id") != section_id]
    after = len(sections)

    if before == after:
        raise HTTPException(status_code=404, detail=f"Section '{section_id}' not found")

    data["sections"] = sections
    _save_yaml(path, data)
    return {"status": "ok", "deleted": section_id, "remaining": after}
