from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence, Optional

# If you see a deprecation warning, you can switch to langchain_chroma Chroma
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

def _persist_dir() -> str:
    root = os.getenv("VECTOR_STORE_PATH", "./src/data/indexes")
    Path(root).mkdir(parents=True, exist_ok=True)
    return root

def _embeddings() -> OpenAIEmbeddings:
    model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    return OpenAIEmbeddings(model=model)

def _get_store(collection_name: str) -> Chroma:
    # Chroma requires alnum, dot, underscore, hyphen; no colon.
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in collection_name)
    return Chroma(collection_name=safe, embedding_function=_embeddings(), persist_directory=_persist_dir())

def add_texts(collection_name: str, ids: Sequence[str], texts: Sequence[str], metadatas: Sequence[Dict[str, Any]]) -> None:
    store = _get_store(collection_name)
    store.add_texts(texts=list(texts), metadatas=list(metadatas), ids=list(ids))
    try:
        store.persist()
    except Exception:
        # Chroma >=0.4 auto-persists; ignore
        pass

def query(collection_name: str, text: str, k: int = 8) -> List[Dict[str, Any]]:
    store = _get_store(collection_name)
    results = store.similarity_search_with_score(text, k=k)
    out: List[Dict[str, Any]] = []
    for doc, score in results:
        out.append({
            "id": doc.metadata.get("id"),
            "text": doc.page_content,
            "metadata": doc.metadata or {},
            "score": float(score) if score is not None else None,
        })
    return out
