from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import shutil
import yaml
import json
from datetime import datetime

router = APIRouter(prefix="/admin/frameworks", tags=["admin-frameworks"])

# backend/src/guidelines/<framework>/{chunks/, source/, prompts.yaml}
GUIDELINES_DIR = Path(__file__).resolve().parents[2] / "guidelines"

_slug_re = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,63}$")


# -----------------------
# Helpers
# -----------------------
def _validate_slug(slug: str) -> str:
    if not isinstance(slug, str) or not slug.strip() or not _slug_re.match(slug.strip()):
        raise HTTPException(
            status_code=400,
            detail="Invalid framework slug. Use 2-64 chars: a-z0-9, '_' or '-', start with a-z0-9.",
        )
    return slug.strip()


def _fw_dir(slug: str) -> Path:
    return GUIDELINES_DIR / slug


def _chunks_dir(slug: str) -> Path:
    return _fw_dir(slug) / "chunks"


def _source_dir(slug: str) -> Path:
    return _fw_dir(slug) / "source"


def _prompts_path(slug: str) -> Path:
    return _fw_dir(slug) / "prompts.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid YAML: {e}")


def _save_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)


def _default_prompts(display_name: str, framework_slug: str) -> Dict[str, Any]:
    # Small sane default so existing /admin/prompts routes work immediately.
    # You can overwrite later via your existing admin_prompts PATCH endpoints.
    return {
        "overarching": (
            f"You are generating a compliance report for framework '{framework_slug}' "
            f"({display_name}). Use evidence and avoid repetition."
        ),
        "sections": [
            {
                "id": "exec_summary",
                "name": "Executive Summary",
                "position": 1,
                "default_prompt": "Summarize scope, key risks, and top recommendations.",
                "enabled": True,
            },
            {
                "id": "methodology",
                "name": "Methodology",
                "position": 2,
                "default_prompt": "Explain the assessment methodology and how evidence was used.",
                "enabled": True,
            },
            {
                "id": "gaps",
                "name": "Gap Analysis",
                "position": 3,
                "default_prompt": "Identify gaps, severity, and remediation recommendations.",
                "enabled": True,
            },
        ],
    }


def _ensure_framework_exists(slug: str) -> None:
    if not _fw_dir(slug).exists():
        raise HTTPException(status_code=404, detail=f"Framework not found: {slug}")


# -----------------------
# APIs
# -----------------------

@router.get("")
def list_frameworks():
    """
    Lists framework folders under guidelines/.
    """
    if not GUIDELINES_DIR.exists():
        return {"frameworks": []}

    out: List[Dict[str, Any]] = []
    for p in sorted(GUIDELINES_DIR.iterdir(), key=lambda x: x.name):
        if not p.is_dir() or p.name.startswith("."):
            continue
        slug = p.name
        out.append({
            "slug": slug,
            "has_prompts": _prompts_path(slug).exists(),
            "has_chunks": _chunks_dir(slug).exists(),
            "has_source": _source_dir(slug).exists(),
            "source_files": [f.name for f in _source_dir(slug).glob("*") if f.is_file()] if _source_dir(slug).exists() else [],
        })
    return {"frameworks": out}


@router.post("")
def create_framework(body: Dict[str, Any]):
    """
    1) Create framework skeleton (folders only).
    Does NOT upload methodology, does NOT create prompts unless requested.

    Body:
    {
      "slug": "osfi_b13",
      "create_prompts": true,          # optional (default false)
      "display_name": "OSFI B-13",     # optional
      "clone_prompts_from": "seal"     # optional (if create_prompts true)
    }
    """
    slug = _validate_slug(body.get("slug"))
    create_prompts = bool(body.get("create_prompts", False))
    display_name = body.get("display_name") or slug
    clone_from = body.get("clone_prompts_from")

    if not isinstance(display_name, str) or not display_name.strip():
        raise HTTPException(status_code=400, detail="display_name must be a non-empty string")
    display_name = display_name.strip()

    if clone_from is not None:
        clone_from = _validate_slug(clone_from)

    fw = _fw_dir(slug)
    if fw.exists():
        raise HTTPException(status_code=400, detail=f"Framework already exists: {slug}")

    # create skeleton
    fw.mkdir(parents=True, exist_ok=True)
    _chunks_dir(slug).mkdir(parents=True, exist_ok=True)
    _source_dir(slug).mkdir(parents=True, exist_ok=True)

    # optionally create prompts.yaml
    if create_prompts:
        if clone_from:
            src = _prompts_path(clone_from)
            if not src.exists():
                raise HTTPException(status_code=404, detail=f"clone_prompts_from prompts.yaml not found: {clone_from}")
            shutil.copyfile(src, _prompts_path(slug))
        else:
            _save_yaml(_prompts_path(slug), _default_prompts(display_name, slug))

    return {
        "status": "ok",
        "created": slug,
        "created_prompts": bool(create_prompts),
    }


@router.post("/{framework}/methodology")
def upload_methodology(
    framework: str,
    file: UploadFile = File(...),
    overwrite: bool = True,
):
    """
    2) Upload/replace ONE methodology file into guidelines/<framework>/source/.

    - Accepts only PDFs.
    - Saves as the uploaded filename by default.
    - If overwrite=false and file exists => 409

    Query:
      overwrite=true|false

    Form-data:
      file: <PDF>
    """
    framework = _validate_slug(framework)
    _ensure_framework_exists(framework)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Methodology file must be a .pdf")

    src_dir = _source_dir(framework)
    src_dir.mkdir(parents=True, exist_ok=True)

    dest = src_dir / Path(file.filename).name
    if dest.exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"File already exists: {dest.name}")

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"status": "ok", "framework": framework, "saved": f"source/{dest.name}"}


@router.get("/{framework}/methodology")
def list_methodology_files(framework: str):
    """
    List files under guidelines/<framework>/source/
    """
    framework = _validate_slug(framework)
    _ensure_framework_exists(framework)

    src_dir = _source_dir(framework)
    files = [p.name for p in src_dir.glob("*") if p.is_file()] if src_dir.exists() else []
    return {"framework": framework, "files": files}


@router.put("/{framework}/prompts")
def put_prompts(framework: str, body: Dict[str, Any]):
    """
    3a) Replace the entire prompts.yaml in one shot.

    Body must match your current schema:
    { "overarching": "...", "sections": [...] }
    """
    framework = _validate_slug(framework)
    _ensure_framework_exists(framework)

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")
    if "overarching" in body and not isinstance(body["overarching"], str):
        raise HTTPException(status_code=400, detail="'overarching' must be a string")
    if "sections" in body and not isinstance(body["sections"], list):
        raise HTTPException(status_code=400, detail="'sections' must be a list")

    _save_yaml(_prompts_path(framework), body)
    return {"status": "ok", "framework": framework, "updated": "prompts.yaml"}


@router.post("/{framework}/prompts/default")
def create_default_prompts(framework: str, body: Optional[Dict[str, Any]] = None):
    """
    3b) Create prompts.yaml with defaults (or overwrite).

    Body (optional):
    { "display_name": "OSFI B-13" , "overwrite": true }
    """
    framework = _validate_slug(framework)
    _ensure_framework_exists(framework)

    body = body or {}
    display_name = body.get("display_name") or framework
    overwrite = bool(body.get("overwrite", True))

    p = _prompts_path(framework)
    if p.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="prompts.yaml already exists")

    _save_yaml(p, _default_prompts(str(display_name), framework))
    return {"status": "ok", "framework": framework, "created": "prompts.yaml"}


@router.post("/{framework}/prompts/clone")
def clone_prompts(framework: str, body: Dict[str, Any]):
    """
    3c) Clone prompts.yaml from another framework.

    Body:
    { "from": "seal", "overwrite": true }
    """
    framework = _validate_slug(framework)
    _ensure_framework_exists(framework)

    src_fw = _validate_slug(body.get("from"))
    overwrite = bool(body.get("overwrite", True))

    src = _prompts_path(src_fw)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Source prompts.yaml not found for: {src_fw}")

    dst = _prompts_path(framework)
    if dst.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="prompts.yaml already exists")

    shutil.copyfile(src, dst)
    return {"status": "ok", "framework": framework, "cloned_from": src_fw}
