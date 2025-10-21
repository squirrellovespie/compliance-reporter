from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Optional, Tuple

# If you see a deprecation warning, you can switch to langchain_chroma Chroma
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings


# -----------------------------
# Persistence / store helpers
# -----------------------------
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
    return Chroma(
        collection_name=safe,
        embedding_function=_embeddings(),
        persist_directory=_persist_dir(),
    )


# -----------------------------
# Public: add_texts
# -----------------------------
def add_texts(
    collection_name: str,
    ids: Sequence[str],
    texts: Sequence[str],
    metadatas: Sequence[Dict[str, Any]],
) -> None:
    store = _get_store(collection_name)
    store.add_texts(texts=list(texts), metadatas=list(metadatas), ids=list(ids))
    try:
        store.persist()
    except Exception:
        # Chroma >= 0.4 auto-persists; ignore
        pass


# -----------------------------
# Hybrid helper (keyword score)
# -----------------------------
_token_re = re.compile(r"[A-Za-z0-9_]+")

def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _token_re.findall(text or "")]

def _jaccard(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0

def _normalize(xs: List[float]) -> List[float]:
    if not xs:
        return xs
    lo, hi = min(xs), max(xs)
    if hi <= lo:
        return [0.0 for _ in xs]
    return [(x - lo) / (hi - lo) for x in xs]


# -----------------------------
# Public: query with strategies
# -----------------------------
def query(
    collection_name: str,
    text: str,
    k: int = 8,
    *,
    strategy: str = "cosine",          # "cosine" | "mmr" | "hybrid"
    fetch_k: Optional[int] = None,     # internal pool size for mmr/hybrid (defaults to k*4)
    alpha: float = 0.7,                # hybrid: weight for vector vs lexical (0..1)
    mmr_lambda: float = 0.5,           # mmr: diversification strength (0..1)
) -> List[Dict[str, Any]]:
    """
    Returns a list of dicts: {id, text, metadata, score}

    strategy:
      - "cosine": default vector similarity
      - "mmr": diversified selection via Maximal Marginal Relevance
      - "hybrid": fuse vector score with cheap lexical overlap (Jaccard over tokens)

    Notes:
      * score is float and comparable only within a given strategy call.
      * For MMR, LangChain doesn't always expose similarity scores; we return 1.0.
    """
    store = _get_store(collection_name)
    fetch_k = fetch_k or (k * 4)

    if strategy == "mmr":
        retriever = store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": fetch_k, "lambda_mult": mmr_lambda},
        )
        docs = retriever.invoke(text)
        out: List[Dict[str, Any]] = []
        for d in docs:
            out.append({
                "id": d.metadata.get("id"),
                "text": d.page_content,
                "metadata": d.metadata or {},
                "score": 1.0,  # MMR path doesn't provide consistent scores
            })
        return out

    # Base vector search (cosine) with a larger pool if needed
    pool_k = fetch_k if strategy in ("hybrid",) else k
    docs_with_scores = store.similarity_search_with_score(text, k=pool_k)

    if strategy == "hybrid":
        vec_scores = [float(s) for (_, s) in docs_with_scores]
        lex_scores = [_jaccard(_tokenize(text), _tokenize(d.page_content)) for (d, _) in docs_with_scores]

        vec_n = _normalize(vec_scores)
        lex_n = _normalize(lex_scores)

        fused: List[Tuple[float, Any]] = []
        for (d, _), vs, ls in zip(docs_with_scores, vec_n, lex_n):
            fused_score = alpha * vs + (1.0 - alpha) * ls
            fused.append((fused_score, d))

        fused.sort(key=lambda x: x[0], reverse=True)
        fused = fused[:k]
        out: List[Dict[str, Any]] = []
        for score, d in fused:
            out.append({
                "id": d.metadata.get("id"),
                "text": d.page_content,
                "metadata": d.metadata or {},
                "score": float(score),
            })
        return out

    # Default: cosine top-k
    docs_with_scores = docs_with_scores[:k]
    out: List[Dict[str, Any]] = []
    for d, score in docs_with_scores:
        out.append({
            "id": d.metadata.get("id"),
            "text": d.page_content,
            "metadata": d.metadata or {},
            "score": float(score) if score is not None else None,
        })
    return out
