from __future__ import annotations

"""Lightweight Node Set registry for discoverability and extension."""

from importlib import import_module
from typing import Callable, Dict, Iterable, TypeVar

from .base import NodeSet


RecipeBuilder = Callable[..., NodeSet]
_REGISTRY: Dict[str, RecipeBuilder] = {}
_DISCOVERED = False
_AUTO_IMPORTS: tuple[str, ...] = ("qmtl.runtime.nodesets.recipes",)
_T = TypeVar("_T", bound=RecipeBuilder)


def register(name: str, builder: RecipeBuilder) -> None:
    """Register ``builder`` under ``name``.

    Duplicate registrations for different callables are rejected to avoid
    accidentally shadowing an existing recipe. Re-registering the same callable
    is treated as a no-op to support module reloads in development.
    """

    if not isinstance(name, str) or not name:
        raise ValueError("registry name must be a non-empty string")

    existing = _REGISTRY.get(name)
    if existing is not None and existing is not builder:
        raise ValueError(f"nodeset recipe '{name}' is already registered")
    _REGISTRY[name] = builder


def nodeset_recipe(name: str) -> Callable[[_T], _T]:
    """Decorator that registers a Node Set recipe for discovery."""

    def decorator(builder: _T) -> _T:
        register(name, builder)
        return builder

    return decorator


def _ensure_discovered() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return

    for module_name in _AUTO_IMPORTS:
        import_module(module_name)

    _DISCOVERED = True


def discover(modules: Iterable[str]) -> None:
    """Explicitly import additional modules to trigger recipe registration."""

    for module_name in modules:
        import_module(module_name)


def make(name: str, *args, **kwargs) -> NodeSet:
    _ensure_discovered()
    try:
        builder = _REGISTRY[name]
    except KeyError as e:
        raise KeyError(f"unknown nodeset: {name}") from e
    return builder(*args, **kwargs)


def list_registered() -> list[str]:
    _ensure_discovered()
    return sorted(_REGISTRY.keys())


__all__ = ["discover", "nodeset_recipe", "register", "make", "list_registered"]

