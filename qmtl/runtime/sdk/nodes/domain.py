"""Domain-layer node primitives (no runtime wiring)."""

from __future__ import annotations

from .base import Node
from .processors import ProcessingNode

__all__ = ["Node", "ProcessingNode"]
