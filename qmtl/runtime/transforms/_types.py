from __future__ import annotations

"""Shared typing helpers for transform modules."""

from collections.abc import Mapping
from typing import TypeAlias


# Mapping type used by simple metric-based transforms (e.g., scale).
MetricMapping: TypeAlias = Mapping[str, float]

