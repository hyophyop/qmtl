"""Metrics adapters for the Arrow cache backend."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CacheInstrumentation:
    """Bundle of callbacks used by :class:`NodeCacheArrow`."""

    observe_cache_read: Callable[[str, int], None]
    observe_cross_context_cache_hit: Callable[..., None]
    observe_resident_bytes: Callable[[str, int], None]


def _noop_cache_read(_upstream_id: str, _interval: int) -> None:
    return None


def _noop_cross_context(*_args, **_kwargs) -> None:
    return None


def _noop_resident_bytes(_node_id: str, _resident: int) -> None:
    return None


NOOP_INSTRUMENTATION = CacheInstrumentation(
    observe_cache_read=_noop_cache_read,
    observe_cross_context_cache_hit=_noop_cross_context,
    observe_resident_bytes=_noop_resident_bytes,
)


def default_instrumentation() -> CacheInstrumentation:
    """Return instrumentation backed by ``qmtl.runtime.sdk.metrics``."""

    from .. import metrics as sdk_metrics

    return CacheInstrumentation(
        observe_cache_read=sdk_metrics.observe_cache_read,
        observe_cross_context_cache_hit=sdk_metrics.observe_cross_context_cache_hit,
        observe_resident_bytes=sdk_metrics.observe_nodecache_resident_bytes,
    )


__all__ = [
    "CacheInstrumentation",
    "NOOP_INSTRUMENTATION",
    "default_instrumentation",
]
