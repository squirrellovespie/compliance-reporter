# backend/src/assessors/registry.py
from __future__ import annotations

from pathlib import Path
from typing import Type, List
import re

from assessors.base import BaseFrameworkAssessor

_slug_re = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,63}$")


def _src_root() -> Path:
    # .../backend/src
    return Path(__file__).resolve().parents[1]


def _guidelines_dir() -> Path:
    return _src_root() / "guidelines"


def _assessors_dir() -> Path:
    return _src_root() / "assessors"


def _validate_slug(slug: str) -> str:
    if not isinstance(slug, str) or not slug.strip() or not _slug_re.match(slug.strip()):
        raise ValueError("Invalid framework slug")
    return slug.strip()


def available_frameworks() -> List[str]:
    gdir = _guidelines_dir()
    if not gdir.exists():
        return []
    out: List[str] = []
    for p in gdir.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            out.append(p.name)
    return sorted(out)


def _taxonomy_path_for(framework: str) -> Path:
    """
    Resolution order (so you can migrate gradually):
      1) guidelines/<framework>/taxonomy.yaml      (new canonical location)
      2) assessors/<framework>/taxonomy.yaml       (legacy)
      3) assessors/_generic/taxonomy.yaml          (fallback default)
    """
    framework = _validate_slug(framework)
    src = _src_root()

    p1 = src / "guidelines" / framework / "taxonomy.yaml"
    if p1.exists():
        return p1

    p2 = src / "assessors" / framework / "taxonomy.yaml"
    if p2.exists():
        return p2

    p3 = src / "assessors" / "_generic" / "taxonomy.yaml"
    if p3.exists():
        return p3

    return p1  # return the canonical path (even if missing) for clearer errors


def get_assessor(framework: str) -> Type[BaseFrameworkAssessor]:
    """
    Dynamic assessor:
    - If guidelines/<framework>/ exists -> framework is considered valid
    - taxonomy.yaml is resolved via _taxonomy_path_for()
    """
    framework = _validate_slug(framework)
    fw_dir = _guidelines_dir() / framework

    if not fw_dir.exists():
        raise ValueError(f"Unknown framework: {framework}. Available: {available_frameworks()}")

    taxonomy_path = _taxonomy_path_for(framework)

    # Create a tiny dynamic subclass that pins name + taxonomy_path
    class GenericAssessor(BaseFrameworkAssessor):
        name = framework

        def taxonomy_path(self) -> Path:
            return taxonomy_path

    return GenericAssessor