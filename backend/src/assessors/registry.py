from __future__ import annotations
from typing import Dict, Type

from assessors.seal.assessor import Assessor as SealAssessor
from assessors.occ.assessor import Assessor as OccAssessor
from assessors.osfi_b10.assessor import Assessor as B10Assessor
from assessors.osfi_b13.assessor import Assessor as B13Assessor

_REGISTRY: Dict[str, Type] = {
    "seal": SealAssessor,
    "occ": OccAssessor,
    "osfi_b10": B10Assessor,
    "osfi_b13": B13Assessor,
}

def get_assessor(framework: str):
    if framework not in _REGISTRY:
        raise ValueError(f"Unknown framework: {framework}. Available: {sorted(_REGISTRY.keys())}")
    return _REGISTRY[framework]
