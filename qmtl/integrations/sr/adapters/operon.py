"""Operon SR adapter for pyoperon-based GP engine.

This module provides an adapter for the Operon genetic programming engine
(via pyoperon) to convert its outputs into QMTL-compatible candidates.

Note:
    This adapter requires pyoperon to be installed. If pyoperon is not
    available, only the OperonCandidate type definition will be usable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, TYPE_CHECKING

from ..types import BaseSRCandidate

# Type checking imports (won't fail if pyoperon not installed)
if TYPE_CHECKING:
    try:
        import pyoperon  # type: ignore
    except ImportError:
        pass


@dataclass
class OperonCandidate(BaseSRCandidate):
    """Operon-specific SR candidate.

    Extends BaseSRCandidate with Operon-specific metadata fields.

    Attributes:
        tree_depth: Depth of the expression tree
        num_nodes: Number of nodes in the expression tree
        r2_score: R² score from Operon evaluation
        nmse: Normalized mean squared error
    """

    tree_depth: int = 0
    num_nodes: int = 0
    r2_score: float = 0.0
    nmse: float = 0.0

    def get_id(self) -> str:
        """Return the candidate ID."""
        if "id" in self.metadata:
            return str(self.metadata["id"])
        # Generate ID from generation and expression hash
        expr_hash = hash(self.expression) % 10000
        return f"operon_{self.generation}_{expr_hash:04d}"


# Check if pyoperon is available
_PYOPERON_AVAILABLE = False
try:
    import pyoperon  # type: ignore

    _PYOPERON_AVAILABLE = True
except ImportError:
    pyoperon = None  # type: ignore


def is_pyoperon_available() -> bool:
    """Check if pyoperon is installed and available."""
    return _PYOPERON_AVAILABLE


class OperonAdapter:
    """Adapter for converting Operon/pyoperon outputs to QMTL candidates.

    This adapter provides methods to convert pyoperon Individual objects
    and other Operon outputs into OperonCandidate instances.

    Example:
        >>> adapter = OperonAdapter()
        >>> # After running Operon evolution
        >>> candidates = adapter.from_population(population, generation=10)
    """

    def __init__(self, default_fitness: float = 0.0):
        """Initialize the adapter.

        Parameters
        ----------
        default_fitness : float
            Default fitness value if not available from Operon

        Raises
        ------
        ImportError
            If pyoperon is not installed
        """
        if not _PYOPERON_AVAILABLE:
            raise ImportError(
                "pyoperon is required for OperonAdapter. "
                "Install with: pip install pyoperon"
            )
        self.default_fitness = default_fitness

    def from_individual(
        self,
        individual: Any,  # pyoperon.Individual
        *,
        generation: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> OperonCandidate:
        """Convert a pyoperon Individual to OperonCandidate.

        Parameters
        ----------
        individual : pyoperon.Individual
            Operon individual object
        generation : int
            Generation number
        metadata : dict, optional
            Additional metadata to include

        Returns
        -------
        OperonCandidate
            Converted candidate
        """
        # Extract expression string from individual
        # Note: Actual API depends on pyoperon version
        expression = self._extract_expression(individual)

        # Extract fitness/metrics
        raw_fitness: Any = getattr(individual, "fitness", self.default_fitness)
        if hasattr(raw_fitness, "__getitem__"):
            fitness = raw_fitness[0]  # First objective if multi-objective
        else:
            fitness = raw_fitness

        # Build metadata
        meta = metadata.copy() if metadata else {}
        if hasattr(individual, "id"):
            meta["id"] = individual.id

        return OperonCandidate(
            expression=expression,
            metadata=meta,
            fitness=float(fitness),
            complexity=self._extract_complexity(individual),
            generation=generation,
            tree_depth=self._extract_tree_depth(individual),
            num_nodes=self._extract_num_nodes(individual),
            r2_score=self._extract_r2(individual),
            nmse=self._extract_nmse(individual),
        )

    def from_population(
        self,
        population: Sequence[Any],  # Sequence[pyoperon.Individual]
        *,
        generation: int = 0,
    ) -> list[OperonCandidate]:
        """Convert a population of Operon individuals to candidates.

        Parameters
        ----------
        population : Sequence
            List of pyoperon Individual objects
        generation : int
            Generation number

        Returns
        -------
        list[OperonCandidate]
            List of converted candidates
        """
        return [
            self.from_individual(ind, generation=generation)
            for ind in population
        ]

    def from_best_individuals(
        self,
        results: Any,  # pyoperon evolution results
        *,
        top_k: int = 10,
    ) -> list[OperonCandidate]:
        """Extract top-k individuals from Operon evolution results.

        Parameters
        ----------
        results : Any
            Operon evolution results object
        top_k : int
            Number of top individuals to extract

        Returns
        -------
        list[OperonCandidate]
            List of top candidates sorted by fitness
        """
        # Extract best individuals from results
        # Note: Actual API depends on pyoperon version
        if hasattr(results, "best_individuals"):
            individuals = results.best_individuals[:top_k]
        elif hasattr(results, "population"):
            # Sort by fitness and take top-k
            sorted_pop = sorted(
                results.population,
                key=lambda x: getattr(x, "fitness", [0])[0],
                reverse=True,
            )
            individuals = sorted_pop[:top_k]
        else:
            raise ValueError("Cannot extract individuals from results")

        generation = getattr(results, "generation", 0)
        return self.from_population(individuals, generation=generation)

    # -------------------------------------------------------------------------
    # Private extraction methods
    # These may need adjustment based on actual pyoperon API
    # -------------------------------------------------------------------------

    def _extract_expression(self, individual: Any) -> str:
        """Extract expression string from individual."""
        if hasattr(individual, "expression"):
            return str(individual.expression)
        if hasattr(individual, "genotype"):
            return str(individual.genotype)
        if hasattr(individual, "__str__"):
            return str(individual)
        return ""

    def _extract_complexity(self, individual: Any) -> float:
        """Extract complexity measure from individual."""
        if hasattr(individual, "complexity"):
            return float(individual.complexity)
        if hasattr(individual, "length"):
            return float(individual.length)
        return 0.0

    def _extract_tree_depth(self, individual: Any) -> int:
        """Extract tree depth from individual."""
        if hasattr(individual, "tree_depth"):
            return int(individual.tree_depth)
        if hasattr(individual, "depth"):
            return int(individual.depth)
        return 0

    def _extract_num_nodes(self, individual: Any) -> int:
        """Extract number of nodes from individual."""
        if hasattr(individual, "num_nodes"):
            return int(individual.num_nodes)
        if hasattr(individual, "length"):
            return int(individual.length)
        if hasattr(individual, "size"):
            return int(individual.size)
        return 0

    def _extract_r2(self, individual: Any) -> float:
        """Extract R² score from individual."""
        if hasattr(individual, "r2_score"):
            return float(individual.r2_score)
        if hasattr(individual, "r2"):
            return float(individual.r2)
        return 0.0

    def _extract_nmse(self, individual: Any) -> float:
        """Extract NMSE from individual."""
        if hasattr(individual, "nmse"):
            return float(individual.nmse)
        if hasattr(individual, "fitness"):
            # Sometimes fitness is NMSE
            fitness = individual.fitness
            if hasattr(fitness, "__getitem__"):
                return float(fitness[0])
            return float(fitness)
        return 0.0
