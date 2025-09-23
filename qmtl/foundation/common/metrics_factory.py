from __future__ import annotations

"""Utilities for idempotent Prometheus metric registration.

This module centralizes the boilerplate required to fetch-or-create metrics
from a shared registry while keeping test hooks (``_vals``/``_val``) in sync.
It also exposes a registry-aware reset helper so individual modules no longer
need to manipulate Prometheus internals directly.
"""

from collections.abc import Callable, Iterable, Sequence
from typing import Any, Dict, Tuple, TypeVar

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    REGISTRY as global_registry,
)
from prometheus_client.metrics import MetricWrapperBase

__all__ = [
    "get_or_create_counter",
    "get_or_create_gauge",
    "get_or_create_histogram",
    "register_reset_hook",
    "reset_metrics",
]

MetricT = TypeVar("MetricT", bound=MetricWrapperBase)
RegistryKey = Tuple[CollectorRegistry, str]

_METRIC_CACHE: Dict[RegistryKey, MetricWrapperBase] = {}
_RESET_CALLBACKS: Dict[RegistryKey, Callable[[], None]] = {}


def get_or_create_counter(
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None = None,
    *,
    registry: CollectorRegistry | None = None,
    test_value_attr: str | None = None,
    test_value_factory: Callable[[], Any] | None = None,
    reset: Callable[[Counter], None] | None = None,
) -> Counter:
    """Return an existing counter or register a new one."""

    reg = registry or global_registry
    metric = _get_or_create_metric(
        Counter,
        name,
        documentation,
        labelnames,
        registry=reg,
    )
    _ensure_test_attr(metric, test_value_attr, test_value_factory)
    _register_reset(metric, reg, reset, test_value_attr, test_value_factory)
    return metric


def get_or_create_gauge(
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None = None,
    *,
    registry: CollectorRegistry | None = None,
    test_value_attr: str | None = None,
    test_value_factory: Callable[[], Any] | None = None,
    reset: Callable[[Gauge], None] | None = None,
) -> Gauge:
    """Return an existing gauge or register a new one."""

    reg = registry or global_registry
    metric = _get_or_create_metric(
        Gauge,
        name,
        documentation,
        labelnames,
        registry=reg,
    )
    _ensure_test_attr(metric, test_value_attr, test_value_factory)
    _register_reset(metric, reg, reset, test_value_attr, test_value_factory)
    return metric


def get_or_create_histogram(
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None = None,
    *,
    registry: CollectorRegistry | None = None,
    test_value_attr: str | None = None,
    test_value_factory: Callable[[], Any] | None = None,
    reset: Callable[[Histogram], None] | None = None,
) -> Histogram:
    """Return an existing histogram or register a new one."""

    reg = registry or global_registry
    metric = _get_or_create_metric(
        Histogram,
        name,
        documentation,
        labelnames,
        registry=reg,
    )
    _ensure_test_attr(metric, test_value_attr, test_value_factory)
    _register_reset(metric, reg, reset, test_value_attr, test_value_factory)
    return metric


def register_reset_hook(
    name: str,
    callback: Callable[[], None],
    *,
    registry: CollectorRegistry | None = None,
) -> None:
    """Register an additional reset hook for ``name``.

    Hooks registered through this function override any previously registered
    callback for the same registry/name pair. Use this to install bespoke reset
    behaviour for metrics created outside this module.
    """

    reg = registry or global_registry
    _RESET_CALLBACKS[(reg, name)] = callback


def reset_metrics(
    names: Iterable[str] | None = None,
    *,
    registry: CollectorRegistry | None = None,
) -> None:
    """Invoke registered reset callbacks for ``names``.

    When ``names`` is ``None`` every registered metric for ``registry`` is
    reset.
    """

    reg = registry or global_registry
    if names is None:
        keys = [key for key in _RESET_CALLBACKS if key[0] is reg]
    else:
        requested = set(names)
        keys = [key for key in _RESET_CALLBACKS if key[0] is reg and key[1] in requested]
    for key in keys:
        _RESET_CALLBACKS[key]()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_or_create_metric(
    metric_cls: type[MetricT],
    name: str,
    documentation: str,
    labelnames: Sequence[str] | None,
    *,
    registry: CollectorRegistry | None,
) -> MetricT:
    reg = registry or global_registry
    labels = tuple(labelnames or ())
    cache_key = (reg, name)
    cached = _METRIC_CACHE.get(cache_key)
    if cached is not None:
        if isinstance(cached, metric_cls) and _labels_match(cached, labels):
            return cached  # type: ignore[return-value]
        try:
            reg.unregister(cached)
        except Exception:  # pragma: no cover - defensive
            pass
        _METRIC_CACHE.pop(cache_key, None)

    existing = _lookup_metric(reg, name)
    if existing is not None:
        if not isinstance(existing, metric_cls):  # pragma: no cover - defensive
            raise TypeError(
                f"Metric '{name}' already registered with incompatible type {type(existing)!r}"
            )
        if not _labels_match(existing, labels):
            reg.unregister(existing)
            existing = None
    if existing is None:
        metric = metric_cls(name, documentation, labels, registry=reg)
    else:
        metric = existing
    _METRIC_CACHE[cache_key] = metric
    return metric  # type: ignore[return-value]


def _ensure_test_attr(
    metric: MetricWrapperBase,
    attr: str | None,
    factory: Callable[[], Any] | None,
) -> None:
    if not attr:
        return
    if not hasattr(metric, attr):
        creator = factory or dict
        setattr(metric, attr, creator())


def _register_reset(
    metric: MetricWrapperBase,
    registry: CollectorRegistry,
    reset: Callable[[MetricWrapperBase], None] | None,
    test_value_attr: str | None,
    test_value_factory: Callable[[], Any] | None,
) -> None:
    name = getattr(metric, "_name", None)
    if not name:
        return

    def _reset() -> None:
        if reset is not None:
            reset(metric)
        else:
            _default_reset(metric)
        if test_value_attr:
            creator = test_value_factory or dict
            setattr(metric, test_value_attr, creator())

    _RESET_CALLBACKS[(registry, name)] = _reset


def _default_reset(metric: MetricWrapperBase) -> None:
    labelnames = tuple(getattr(metric, "_labelnames", ()))
    if labelnames:
        metric.clear()
        return

    if isinstance(metric, Counter):
        metric._value.set(0)  # type: ignore[attr-defined]
    elif isinstance(metric, Gauge):
        metric.set(0)
    elif isinstance(metric, Histogram):
        metric._sum.set(0)  # type: ignore[attr-defined]
        for bucket in getattr(metric, "_buckets", ()):  # type: ignore[attr-defined]
            bucket.set(0)
    else:  # pragma: no cover - future metric types
        metric.clear()


def _lookup_metric(registry: CollectorRegistry, name: str) -> MetricWrapperBase | None:
    try:
        collectors = registry._names_to_collectors  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - defensive
        return None
    return collectors.get(name)


def _labels_match(metric: MetricWrapperBase, expected: Sequence[str]) -> bool:
    current = tuple(getattr(metric, "_labelnames", ()))
    return current == tuple(expected)


