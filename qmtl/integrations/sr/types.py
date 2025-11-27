"""SR (Strategy Recommendation) integration type definitions.

This module defines the abstract interfaces and base implementations for
SR engine integration with QMTL. All SR engine adapters must comply with
the SRCandidate protocol to ensure interoperability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SRCandidate(Protocol):
    """Abstract interface for SR candidate strategies.

    All SR engine adapters must implement this protocol.
    This ensures QMTL is not coupled to any specific SR engine.

    Attributes:
        expression: The strategy expression string (e.g., "EMA(close, 20) > EMA(close, 50)")
        metadata: Engine-specific metadata dict
        fitness: Fitness/score from the SR engine
    """

    expression: str
    metadata: dict[str, Any]
    fitness: float

    def get_id(self) -> str:
        """Return a unique identifier for this candidate."""
        ...


@dataclass
class BaseSRCandidate:
    """Base implementation of SRCandidate protocol.

    Can be used directly or subclassed for engine-specific candidates.
    """

    expression: str
    metadata: dict[str, Any] = field(default_factory=dict)
    fitness: float = 0.0
    complexity: float = 0.0
    generation: int = 0

    def get_id(self) -> str:
        """Return the candidate ID from metadata, or generate one from expression hash."""
        if "id" in self.metadata:
            return str(self.metadata["id"])
        return f"sr_{hash(self.expression) % 10000:04d}"


@dataclass
class PySRCandidate(BaseSRCandidate):
    """PySR-specific candidate with additional fields.

    Attributes:
        loss: PySR loss value (lower is better)
        node_count: Number of nodes in the expression tree
        equation: Original equation string from PySR
    """

    loss: float = 0.0
    node_count: int = 0
    equation: str = ""

    def __post_init__(self) -> None:
        # Sync equation with expression if not set
        if not self.equation and self.expression:
            self.equation = self.expression
        elif not self.expression and self.equation:
            self.expression = self.equation


@dataclass
class OperonCandidate(BaseSRCandidate):
    """Operon-specific candidate with additional fields.

    Attributes:
        tree_depth: Depth of the expression tree
        num_nodes: Number of nodes in the tree
    """

    tree_depth: int = 0
    num_nodes: int = 0

