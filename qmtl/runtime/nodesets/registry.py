from __future__ import annotations

"""Lightweight Node Set registry for discoverability and extension."""

from typing import Callable, Dict

from .base import NodeSet


_REGISTRY: Dict[str, Callable[..., NodeSet]] = {}


def register(name: str, builder: Callable[..., NodeSet]) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("registry name must be a non-empty string")
    _REGISTRY[name] = builder


def make(name: str, *args, **kwargs) -> NodeSet:
    try:
        builder = _REGISTRY[name]
    except KeyError as e:
        raise KeyError(f"unknown nodeset: {name}") from e
    return builder(*args, **kwargs)


def list_registered() -> list[str]:
    return sorted(_REGISTRY.keys())


def _register_builtins() -> None:
    # Local import to avoid cycles
    from .recipes import make_ccxt_spot_nodeset, make_ccxt_futures_nodeset

    register("ccxt_spot", make_ccxt_spot_nodeset)
    register("ccxt_futures", make_ccxt_futures_nodeset)


_register_builtins()


__all__ = ["register", "make", "list_registered"]

