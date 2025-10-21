from __future__ import annotations
from pathlib import Path
from assessors.base import BaseFrameworkAssessor

class Assessor(BaseFrameworkAssessor):
    name = "osfi_b10"

    def taxonomy_path(self) -> Path:
        # backend/src/assessors/osfi_b10/taxonomy.yaml
        return Path(__file__).resolve().parent / "taxonomy.yaml"
