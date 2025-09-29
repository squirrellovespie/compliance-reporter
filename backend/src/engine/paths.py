# backend/src/engine/paths.py
from __future__ import annotations
from pathlib import Path

def get_src_root() -> Path:
    """
    Returns .../backend/src regardless of where it's called from.
    """
    here = Path(__file__).resolve()
    # engine/ -> src
    return here.parents[1]

def guidelines_dir() -> Path:
    return get_src_root() / "guidelines"

def data_dir() -> Path:
    return get_src_root() / "data"

def uploads_dir(firm: str) -> Path:
    return data_dir() / "uploads" / firm

def indexes_dir() -> Path:
    return get_src_root() / "data" / "indexes"
