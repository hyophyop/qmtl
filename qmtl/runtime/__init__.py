"""Runtime components for strategy execution."""

from __future__ import annotations

import importlib

__all__ = [
    "brokerage",
    "generators",
    "indicators",
    "io",
    "labeling",
    "nodesets",
    "pipeline",
    "reference_models",
    "sdk",
    "transforms",
]

_MODULES = {
    name: f"qmtl.runtime.{name}"
    for name in __all__
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
