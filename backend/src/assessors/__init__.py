from __future__ import annotations
from importlib import import_module
from types import ModuleType
from typing import Dict, Type, Any

class _Registry:
    def __init__(self) -> None:
        self._map: Dict[str, Type[Any]] = {}
        self._loaded = False

    def _maybe_load_pkg(self, pkg: str) -> None:
        """
        Try to import assessors.<pkg>.assessor and register its Assessor class.
        """
        try:
            mod: ModuleType = import_module(f"{__name__}.{pkg}.assessor")
        except ModuleNotFoundError:
            return
        cls = getattr(mod, "Assessor", None)
        if cls is None:
            return
        name = getattr(cls, "name", pkg)  # fallback to package name
        self._map[name] = cls

    def load_all(self) -> None:
        if self._loaded:
            return
        # Explicit list keeps things predictable. Add new frameworks here.
        for pkg in ("seal", "occ", "osfi_b10", "osfi_b13"):
            self._maybe_load_pkg(pkg)
        self._loaded = True

    def get(self, name: str):
        if not self._loaded:
            self.load_all()
        try:
            return self._map[name]
        except KeyError:
            raise KeyError(f"Assessor '{name}' not found. Loaded: {list(self._map.keys())}")

# This is what orchestrator imports:
registry = _Registry()
