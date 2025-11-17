"""Scale the average metric."""

# Source: ../docs/alphadocs/basic_sequence_pipeline.md

from __future__ import annotations

from ._types import MetricMapping


def scale_transform_node(metric: MetricMapping, factor: float = 2.0) -> float:
    """Return the ``average`` metric scaled by ``factor``."""
    return float(metric["average"] * factor)
