"""Developer-facing interfaces such as CLI tools and scripts."""

from __future__ import annotations

import importlib

__all__ = ["cli", "scripts", "tools", "scaffold"]

_MODULES = {
    "cli": "qmtl.interfaces.cli",
    "scripts": "qmtl.interfaces.scripts",
    "tools": "qmtl.interfaces.tools",
    "scaffold": "qmtl.interfaces.scaffold",
}


def __getattr__(name: str):
    module_path = _MODULES.get(name)
    if module_path is None:
        raise AttributeError(name)
    module = importlib.import_module(module_path)
    globals()[name] = module
    return module


def __dir__():
    return sorted(set(__all__))
