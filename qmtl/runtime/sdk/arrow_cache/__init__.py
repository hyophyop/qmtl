"""Composable Arrow cache backend."""
from __future__ import annotations

from .backend import NodeCacheArrow
from .dependencies import (
    ARROW_AVAILABLE,
    ARROW_CACHE_ENABLED,
    RAY_AVAILABLE,
    pa,
    ray,
)
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
]
