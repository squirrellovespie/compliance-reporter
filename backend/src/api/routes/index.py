from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pathlib import Path
import traceback
from typing import Any, Dict

from engine.indexer import index_framework

router = APIRouter(prefix="/index", tags=["index"])

def get_src_root() -> Path:
    # .../backend/src
    return Path(__file__).resolve().parents[2]

@router.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}

@router.post("/framework/{framework}")
def index_fw(framework: str):
    try:
        info = index_framework(framework, get_src_root())
        return {"framework": framework, **info}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
