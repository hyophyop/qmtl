"""Compatibility helpers for maintaining deprecated import paths."""

from __future__ import annotations

import importlib
import sys
import types
import warnings
from typing import Any


def deprecated_module(alias: str, target: str) -> types.ModuleType:
    """Import *target* and register it under *alias*, emitting a warning."""

    module = importlib.import_module(target)
    warnings.warn(
        f"Importing '{alias}' is deprecated; use '{target}' instead.",
        DeprecationWarning,
        stacklevel=3,
    )
    sys.modules[alias] = module
    return module


def mirror_module_globals(
    target: types.ModuleType, namespace: dict[str, Any], *, alias: str
) -> None:
    """Populate *namespace* with public attributes from *target*.

    This preserves ``__all__`` semantics when redirecting deprecated modules.
    """

    public = getattr(target, "__all__", None)
    if public is None:
        namespace.update({k: v for k, v in vars(target).items() if not k.startswith("_")})
    else:
        namespace.update({name: getattr(target, name) for name in public})

    namespace.update({
        "__doc__": target.__doc__,
        "__file__": getattr(target, "__file__", None),
        "__path__": getattr(target, "__path__", None),
        "__spec__": getattr(target, "__spec__", None),
    })
    namespace["__name__"] = alias
    namespace["__package__"] = alias.rpartition(".")[0] if "." in alias else ""
