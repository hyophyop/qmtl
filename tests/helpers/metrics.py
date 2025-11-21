from __future__ import annotations

"""Shared helpers for accessing Prometheus test stores in assertions."""

from collections.abc import MutableMapping
from typing import Any, Callable

from prometheus_client.metrics import MetricWrapperBase

from qmtl.foundation.common.metrics_factory import get_mapping_store, get_test_store

MappingFactory = Callable[[], MutableMapping[Any, Any]]


def mapping_store(metric: MetricWrapperBase, factory: MappingFactory | None = None) -> MutableMapping[Any, Any]:
    """Return the mapping-backed test store for ``metric``."""

    return get_mapping_store(metric, factory or dict)


def test_value(metric: MetricWrapperBase, factory: Callable[[], Any] | None = None) -> Any:
    """Return the scalar test store value for ``metric`` if present."""

    return get_test_store(metric, factory)  # May be ``None`` if no store is registered.
