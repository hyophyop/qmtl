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

ARROW_AVAILABLE = pa is not None
RAY_AVAILABLE = ray is not None
ARROW_CACHE_ENABLED = ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1"

__all__ = [
    "pa",
    "ray",
    "ARROW_AVAILABLE",
    "RAY_AVAILABLE",
    "ARROW_CACHE_ENABLED",
]
