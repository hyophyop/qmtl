"""Optional dependency guards for Arrow cache backend."""
from __future__ import annotations

import os
from typing import Any

from .. import configuration

pa: Any | None = None
try:  # pragma: no cover - optional dependency
    import pyarrow as pa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pa = None

ray: Any | None = None
try:  # pragma: no cover - optional dependency
    import ray  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ray = None

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
