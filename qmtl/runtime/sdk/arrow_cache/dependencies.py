"""Optional dependency guards for Arrow cache backend."""
from __future__ import annotations

import importlib
import importlib.util
import os
from typing import Any

from .. import configuration

def _load_optional_module(name: str) -> Any | None:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return None
    try:
        return importlib.import_module(name)
    except Exception:
        return None


pa: Any | None = _load_optional_module("pyarrow")
ray: Any | None = _load_optional_module("ray")

def _resolve_enabled() -> bool:
    if pa is None:
        return False
    env_override = os.getenv("QMTL_ARROW_CACHE")
    if env_override is not None:
        normalized = env_override.strip().lower()
        return normalized not in {"", "0", "false", "no", "off"}
    unified = configuration.get_runtime_config()
    if unified is None:
        return False
    return bool(unified.cache.arrow_cache_enabled)


ARROW_AVAILABLE = pa is not None
RAY_AVAILABLE = ray is not None
ARROW_CACHE_ENABLED = _resolve_enabled()


def reload() -> bool:
    """Refresh cached availability toggles after configuration updates."""

    global ARROW_CACHE_ENABLED
    ARROW_CACHE_ENABLED = _resolve_enabled()
    return ARROW_CACHE_ENABLED


__all__ = [
    "pa",
    "ray",
    "ARROW_AVAILABLE",
    "RAY_AVAILABLE",
    "ARROW_CACHE_ENABLED",
    "reload",
]
