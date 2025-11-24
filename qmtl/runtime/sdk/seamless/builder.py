from __future__ import annotations

"""Composable builder utilities for Seamless data providers.

The goal is to let concrete integrations (CCXT, equities, etc.) assemble
Seamless providers by wiring storage, backfill, live, and governance
components without hard-coding those decisions inside provider subclasses.
"""

import importlib
from dataclasses import dataclass, field
from typing import Callable, Dict, Generic, Mapping, Optional, Protocol, TypeVar, cast

from qmtl.runtime.sdk.artifacts import ArtifactRegistrar
from qmtl.runtime.sdk.seamless_data_provider import (
    AutoBackfiller,
    DataSource,
    LiveDataFeed,
)

T_co = TypeVar("T_co", covariant=True)


class ComponentFactory(Protocol, Generic[T_co]):
    """Callable that produces a component instance when invoked."""

    def __call__(self) -> T_co:  # pragma: no cover - interface definition
        ...


def _normalize_factory(value: Optional[Callable[[], T_co] | T_co]) -> Optional[ComponentFactory[T_co]]:
    if value is None:
        return None
    if callable(value):
        return cast(ComponentFactory[T_co], value)
    return cast(ComponentFactory[T_co], lambda: value)


def _instantiate(name: str, factory: Optional[ComponentFactory[T_co]]) -> Optional[T_co]:
    if factory is None:
        return None
    try:
        return factory()
    except Exception as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(f"failed to build seamless component '{name}'") from exc


@dataclass(slots=True)
class SeamlessAssembly:
    """Concrete component instances ready to feed into SeamlessDataProvider."""

    cache_source: Optional[DataSource] = None
    storage_source: Optional[DataSource] = None
    backfiller: Optional[AutoBackfiller] = None
    live_feed: Optional[LiveDataFeed] = None
    registrar: Optional[ArtifactRegistrar] = None


@dataclass(slots=True)
class SeamlessBuilder:
    """Builder used to assemble Seamless providers from pluggable parts."""

    cache: Optional[ComponentFactory[DataSource]] = field(default=None)
    storage: Optional[ComponentFactory[DataSource]] = field(default=None)
    backfill: Optional[ComponentFactory[AutoBackfiller]] = field(default=None)
    live: Optional[ComponentFactory[LiveDataFeed]] = field(default=None)
    registrar: Optional[ComponentFactory[ArtifactRegistrar]] = field(default=None)

    def with_cache(self, component: Optional[Callable[[], DataSource] | DataSource]) -> "SeamlessBuilder":
        self.cache = _normalize_factory(component)
        return self

    def with_storage(self, component: Optional[Callable[[], DataSource] | DataSource]) -> "SeamlessBuilder":
        self.storage = _normalize_factory(component)
        return self

    def with_backfill(self, component: Optional[Callable[[], AutoBackfiller] | AutoBackfiller]) -> "SeamlessBuilder":
        self.backfill = _normalize_factory(component)
        return self

    def with_live(self, component: Optional[Callable[[], LiveDataFeed] | LiveDataFeed]) -> "SeamlessBuilder":
        self.live = _normalize_factory(component)
        return self

    def with_registrar(
        self,
        component: Optional[Callable[[], ArtifactRegistrar] | ArtifactRegistrar],
    ) -> "SeamlessBuilder":
        self.registrar = _normalize_factory(component)
        return self

    def build(self) -> SeamlessAssembly:
        """Materialize the configured components into concrete instances."""

        return SeamlessAssembly(
            cache_source=_instantiate("cache", self.cache),
            storage_source=_instantiate("storage", self.storage),
            backfiller=_instantiate("backfill", self.backfill),
            live_feed=_instantiate("live", self.live),
            registrar=_instantiate("registrar", self.registrar),
        )


PresetFactory = Callable[["SeamlessBuilder", Mapping[str, object]], "SeamlessBuilder"]


class SeamlessPresetRegistry:
    """Global registry mapping preset names to builder customisations."""

    _presets: Dict[str, PresetFactory] = {}
    _loaded: bool = False

    @classmethod
    def register(cls, name: str, factory: PresetFactory) -> None:
        cls._presets[name] = factory

    @classmethod
    def apply(
        cls,
        name: str,
        *,
        builder: Optional["SeamlessBuilder"] = None,
        config: Optional[Mapping[str, object]] = None,
    ) -> "SeamlessBuilder":
        cls._ensure_presets_loaded()
        if name not in cls._presets:
            raise KeyError(f"unknown seamless preset: {name}")
        base = builder or SeamlessBuilder()
        cfg = config or {}
        return cls._presets[name](base, cfg)

    @classmethod
    def _ensure_presets_loaded(cls) -> None:
        if cls._loaded:
            return
        try:
            importlib.import_module("qmtl.runtime.io.seamless_presets")
        finally:
            cls._loaded = True


__all__ = [
    "ComponentFactory",
    "SeamlessAssembly",
    "SeamlessBuilder",
    "SeamlessPresetRegistry",
]
