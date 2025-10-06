from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from engine.prompt_store import load_prompts

from engine.sections_store import (
    load_sections, upsert_sections, delete_section, seed_defaults
)

router = APIRouter(prefix="/sections", tags=["sections"])

class UpsertBody(BaseModel):
    framework: str
    sections: List[dict]  # [{id,name,position,prompt}]

@router.get("/{framework}")
def list_sections(framework: str):
    try:
        data = load_prompts(framework)
        return {
            "framework": framework,
            "overarching_prompt": data.get("overarching",""),
            "sections": data.get("sections", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upsert")
def upsert(body: UpsertBody):
    if not body.sections:
        raise HTTPException(status_code=400, detail="sections cannot be empty")
    out = upsert_sections(body.framework, body.sections)
    return {"framework": body.framework, "sections": [s.__dict__ for s in out]}

@router.delete("/{framework}/{section_id}")
def delete(framework: str, section_id: str):
    out = delete_section(framework, section_id)
    return {"framework": framework, "sections": [s.__dict__ for s in out]}

@router.post("/seed/{framework}")
def seed(framework: str):
    out = seed_defaults(framework)
    return {"framework": framework, "sections": [s.__dict__ for s in out]}
