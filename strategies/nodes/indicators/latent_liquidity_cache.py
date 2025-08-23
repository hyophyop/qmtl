"""Shared cache helpers for latent liquidity indicators."""

from collections.abc import Mapping

CACHE_NS = "latent_liquidity"


def _cache_category(cache: Mapping, name: str) -> dict:
    ns = cache.setdefault(CACHE_NS, {})  # type: ignore[arg-type]
    return ns.setdefault(name, {})  # type: ignore[return-value]

__all__ = ["CACHE_NS", "_cache_category"]
