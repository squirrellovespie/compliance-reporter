from __future__ import annotations
from pathlib import Path
from assessors.base import BaseFrameworkAssessor

class Assessor(BaseFrameworkAssessor):
    name = "seal"

    def taxonomy_path(self) -> Path:
        # backend/src/assessors/seal/taxonomy.yaml
        return Path(__file__).resolve().parent / "taxonomy.yaml"
