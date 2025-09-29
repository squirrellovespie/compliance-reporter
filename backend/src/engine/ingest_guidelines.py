# backend/src/engine/ingest_guidelines.py
from __future__ import annotations
import argparse, json, hashlib, os, sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

# --- deps: PyMuPDF + tiktoken (already in your reqs.txt) ---
import fitz  # PyMuPDF
import tiktoken

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def normalize_ws(s: str) -> str:
    return " ".join(s.split())

def pdf_to_pages_text(pdf_path: Path) -> List[Tuple[int, str]]:
    """Return list of (page_number, text)."""
    pages = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            pages.append((i + 1, normalize_ws(text)))
    return pages

def chunk_by_tokens(text: str, enc, chunk_size: int, overlap: int) -> List[str]:
    """
    Greedy token-based chunker with overlap.
    """
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        piece = enc.decode(tokens[start:end])
        chunks.append(piece)
        if end == len(tokens):
            break
        # next window start with overlap
        start = max(0, end - overlap)
    return chunks

def chunk_pages(framework_dir: Path, framework: str, chunk_size: int, overlap: int) -> Dict[str, Any]:
    source_dir = framework_dir / "source"
    chunks_dir = framework_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    enc = tiktoken.get_encoding("cl100k_base")
    out_path = chunks_dir / "chunks.jsonl"
    manifest_path = chunks_dir / "manifest.json"

    total_chunks = 0
    written_files = []
    with out_path.open("w", encoding="utf-8") as outf:
        for pdf in sorted(source_dir.glob("*.pdf")):
            pages = pdf_to_pages_text(pdf)
            for page_num, page_text in pages:
                if not page_text.strip():
                    continue
                # chunk this page
                parts = chunk_by_tokens(page_text, enc, chunk_size=chunk_size, overlap=overlap)
                for idx, part in enumerate(parts, start=1):
                    record = {
                        "framework": framework,
                        "source_pdf": pdf.name,
                        "page": page_num,
                        "chunk_index": idx,
                        "text": part,
                        # ids/hashes to enable auditable citations later
                        "sha256": sha256_text(f"{pdf.name}:{page_num}:{idx}:{part[:64]}"),
                    }
                    outf.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_chunks += 1
            written_files.append(pdf.name)

    manifest = {
        "framework": framework,
        "source_files": written_files,
        "chunk_file": str(out_path.name),
        "chunk_count": total_chunks,
        "chunk_size_tokens": chunk_size,
        "overlap_tokens": overlap,
    }
    with manifest_path.open("w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)

    return manifest

def main():
    parser = argparse.ArgumentParser(description="Chunk guideline PDFs into JSONL.")
    parser.add_argument("--framework", required=True, help="osfi_b13 | osfi_b10 | occ | seal")
    parser.add_argument("--chunk-size", type=int, default=500, help="target tokens per chunk")
    parser.add_argument("--overlap", type=int, default=80, help="token overlap between chunks")
    args = parser.parse_args()

    here = Path(__file__).resolve()
    candidates = [
        here.parents[1],                 # .../backend/src
        here.parents[2] / "src",         # .../backend/src (alt mount)
        here.parents[2],                 # .../backend       (fallback)
    ]
    repo_root = None
    for cand in candidates:
        if (cand / "guidelines").exists():
            repo_root = cand
            break
    if repo_root is None:
        print(f"✗ Could not find guidelines root near {here}", file=sys.stderr)
        sys.exit(1)

    fw_dir = repo_root / "guidelines" / args.framework
    src_dir = fw_dir / "source"

    if not src_dir.exists():
        print(f"✗ No source dir found at: {src_dir}", file=sys.stderr)
        sys.exit(1)
    if not any(src_dir.glob("*.pdf")):
        print(f"✗ No PDFs found under: {src_dir}", file=sys.stderr)
        sys.exit(1)

    manifest = chunk_pages(fw_dir, args.framework, args.chunk_size, args.overlap)
    print(f"✓ Chunked {manifest['chunk_count']} chunks for {args.framework}")
    print(f"  → {fw_dir/'chunks'/'chunks.jsonl'}")
    print(f"  → {fw_dir/'chunks'/'manifest.json'}")

if __name__ == "__main__":
    main()
