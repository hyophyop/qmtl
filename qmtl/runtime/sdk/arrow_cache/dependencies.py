"""Optional dependency guards for Arrow cache backend."""
from __future__ import annotations

import os

try:  # pragma: no cover - optional dependency
    import pyarrow as pa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pa = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import ray  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ray = None  # type: ignore

from .. import configuration

_FALSE_SENTINELS = {"", "0", "false", "no", "off"}


def _env_override() -> bool | None:
    value = os.getenv("QMTL_ARROW_CACHE")
    if value is None:
        return None
    return value.strip().lower() not in _FALSE_SENTINELS


def _resolve_enabled() -> bool:
    if pa is None:
        return False
    override = _env_override()
    if override is not None:
        return override
    try:
        return bool(configuration.cache_config().arrow_cache_enabled)
    except Exception:  # pragma: no cover - defensive catch
        return False


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
