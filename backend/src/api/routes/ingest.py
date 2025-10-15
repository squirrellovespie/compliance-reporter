from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Dict, Any
from pathlib import Path
import traceback

from engine.indexer import index_assessment_pdf, index_evidence_file, index_evidence_batch

router = APIRouter(prefix="/ingest", tags=["ingest"])

def _uploads_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "uploads"

@router.post("/assessment")
async def ingest_assessment(firm: str = Form(...), file: UploadFile = File(...)):
    try:
        root = _uploads_root()
        root.mkdir(parents=True, exist_ok=True)
        dst = root / f"{firm}__{file.filename}"
        with dst.open("wb") as f:
            f.write(await file.read())
        info = index_assessment_pdf(firm, dst)
        return {"doc_id": dst.name, **info}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/evidence")
async def ingest_evidence(firm: str = Form(...), file: UploadFile = File(...)):
    """Single-file evidence ingest (kept for backward compatibility)."""
    try:
        root = _uploads_root()
        root.mkdir(parents=True, exist_ok=True)
        dst = root / f"{firm}__{file.filename}"
        with dst.open("wb") as f:
            f.write(await file.read())
        info = index_evidence_file(firm, dst)
        return {"doc_id": dst.name, **info}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/evidence-batch")
async def ingest_evidence_batch(firm: str = Form(...), files: List[UploadFile] = File(...)):
    """
    Multi-file evidence ingest. Accepts PDFs, TXT, DOCX, XLSX/CSV, and images (PNG/JPG/TIFF).
    """
    try:
        root = _uploads_root()
        root.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for uf in files:
            dst = root / f"{firm}__{uf.filename}"
            with dst.open("wb") as f:
                f.write(await uf.read())
            saved_paths.append(dst)

        summary = index_evidence_batch(firm, saved_paths)
        # shape: {"total_docs": int, "total_chunks": int, "files": [{file, chunks, status, error?}, ...]}
        return summary
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
