"""Composable Arrow cache backend."""
from __future__ import annotations

from .backend import NodeCacheArrow
from . import dependencies as _dependencies

ARROW_AVAILABLE = _dependencies.ARROW_AVAILABLE
RAY_AVAILABLE = _dependencies.RAY_AVAILABLE
pa = _dependencies.pa
ray = _dependencies.ray
ARROW_CACHE_ENABLED = _dependencies.ARROW_CACHE_ENABLED


def reload_arrow_cache() -> bool:
    """Refresh configuration-driven availability flags."""

    global ARROW_CACHE_ENABLED
    result = _dependencies.reload()
    ARROW_CACHE_ENABLED = _dependencies.ARROW_CACHE_ENABLED
    return result
from .eviction import (
    EvictionStrategy,
    RayEvictionStrategy,
    ThreadedEvictionStrategy,
    create_default_eviction_strategy,
)
from .instrumentation import CacheInstrumentation, NOOP_INSTRUMENTATION, default_instrumentation
from .slices import _Slice, _SliceView
from .view import ArrowCacheView

__all__ = [
    "NodeCacheArrow",
    "ArrowCacheView",
    "_Slice",
    "_SliceView",
    "CacheInstrumentation",
    "NOOP_INSTRUMENTATION",
    "default_instrumentation",
    "EvictionStrategy",
    "ThreadedEvictionStrategy",
    "RayEvictionStrategy",
    "create_default_eviction_strategy",
    "ARROW_AVAILABLE",
    "RAY_AVAILABLE",
    "ARROW_CACHE_ENABLED",
    "pa",
    "ray",
    "reload_arrow_cache",
]
