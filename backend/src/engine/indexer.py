from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import json
import os

from services.vector_langchain import add_texts

# Where evidence/assessments/uploads live
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
UPLOADS_DIR = DATA_DIR / "uploads"

def _ensure_key():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; embeddings cannot be created.")

def index_framework(framework: str, src_root: Path) -> Dict:
    """
    Load pre-chunked guideline JSONL and embed into Chroma.
    Expects: backend/src/guidelines/<framework>/chunks/chunks.jsonl
    """
    _ensure_key()
    chunks_file = src_root / "guidelines" / framework / "chunks" / "chunks.jsonl"
    if not chunks_file.exists():
        raise FileNotFoundError(f"No chunks found at {chunks_file}")

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict] = []

    with chunks_file.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            rec = json.loads(line)
            ids.append(f"{framework}-{i}")
            docs.append(rec.get("text", ""))
            meta = {
                "framework": framework,
                "source_pdf": rec.get("source_pdf"),
                "page": rec.get("page"),
                "chunk_index": rec.get("chunk_index"),
            }
            metas.append(meta)

    add_texts(collection_name=f"fw_{framework}", ids=ids, texts=docs, metadatas=metas)
    return {"count": len(ids)}

def index_assessment_pdf(firm: str, pdf_path: Path) -> Dict:
    """
    Basic per-page text extraction & index (PyMuPDF).
    """
    _ensure_key()
    import fitz  # PyMuPDF
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            if not text:
                continue
            ids.append(f"assess_{firm}_{pdf_path.name}_{i}")
            docs.append(text)
            metas.append({"firm": firm, "page": i, "doc_id": pdf_path.name, "kind": "assessment"})
    add_texts(collection_name=f"assessment_{firm}", ids=ids, texts=docs, metadatas=metas)
    return {"count": len(ids)}

def index_evidence_file(firm: str, file_path: Path) -> Dict:
    """
    Accept .pdf or .txt evidence; index text by page (pdf) or as one block (txt).
    """
    _ensure_key()
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict] = []

    if file_path.suffix.lower() == ".pdf":
        import fitz
        with fitz.open(file_path) as doc:
            for i, page in enumerate(doc, start=1):
                text = (page.get_text("text") or "").strip()
                if not text:
                    continue
                ids.append(f"evid_{firm}_{file_path.name}_{i}")
                docs.append(text)
                metas.append({"firm": firm, "page": i, "doc_id": file_path.name, "kind": "evidence"})
    else:
        # treat as plain text
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        if text:
            ids.append(f"evid_{firm}_{file_path.name}_1")
            docs.append(text)
            metas.append({"firm": firm, "page": 1, "doc_id": file_path.name, "kind": "evidence"})

    add_texts(collection_name=f"evidence_{firm}", ids=ids, texts=docs, metadatas=metas)
    return {"count": len(ids)}
