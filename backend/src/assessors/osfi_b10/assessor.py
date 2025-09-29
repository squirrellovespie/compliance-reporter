from __future__ import annotations
from pathlib import Path
import yaml
from typing import Dict, Iterable

from ..base import BaseFrameworkAssessor

class Assessor(BaseFrameworkAssessor):
    name = "osfi_b10"

    def __init__(self):
        super().__init__()
        src_root = Path(__file__).resolve().parents[2]
        tax_path = src_root / "guidelines" / "osfi_b10" / "taxonomy.yaml"
        if not tax_path.exists():
            raise FileNotFoundError(f"taxonomy not found: {tax_path}")
        self.taxonomy: Dict = yaml.safe_load(tax_path.read_text(encoding="utf-8")) or {}

    def _iter_controls(self) -> Iterable[Dict]:
        items = self.taxonomy.get("controls") or self.taxonomy.get("requirements") or []
        for c in items:
            yield c
