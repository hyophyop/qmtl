"""Generic SR adapter for any expression-based SR engine.

This module provides a generic adapter that can convert expression strings
from any SR engine into QMTL-compatible candidates and strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..types import BaseSRCandidate


@dataclass
class GenericCandidate(BaseSRCandidate):
    """Generic SR candidate for any expression-based SR engine.

    This is a flexible candidate class that can be used with any SR engine
    that produces expression strings. It extends BaseSRCandidate with
    additional optional fields.

    Attributes:
        source_engine: Name of the SR engine that produced this candidate
        raw_data: Original data from the SR engine (for debugging/logging)
    """

    source_engine: str = "generic"
    raw_data: dict[str, Any] = field(default_factory=dict)

    def get_id(self) -> str:
        """Return the candidate ID."""
        if "id" in self.metadata:
            return str(self.metadata["id"])
        # Generate ID from engine name and expression hash
        expr_hash = hash(self.expression) % 10000
        return f"{self.source_engine}_{self.generation}_{expr_hash:04d}"


class GenericSRAdapter:
    """Generic adapter for converting SR engine outputs to QMTL candidates.

    This adapter provides flexible conversion methods that work with
    various SR engine output formats. It can be customized with
    extraction functions for different engines.

    Example:
        >>> adapter = GenericSRAdapter(engine_name="my_automl")
        >>> candidates = adapter.from_dict_list([
        ...     {"expr": "x + y", "score": 0.9, "complexity": 2},
        ...     {"expr": "x * y", "score": 0.8, "complexity": 2},
        ... ], expression_key="expr", fitness_key="score")
    """

    def __init__(
        self,
        engine_name: str = "generic",
        default_fitness: float = 0.0,
        default_complexity: float = 0.0,
    ):
        """Initialize the adapter.

        Parameters
        ----------
        engine_name : str
            Name of the SR engine (used in candidate IDs)
        default_fitness : float
            Default fitness value if not provided
        default_complexity : float
            Default complexity value if not provided
        """
        self.engine_name = engine_name
        self.default_fitness = default_fitness
        self.default_complexity = default_complexity

    def from_expression(
        self,
        expression: str,
        *,
        fitness: float | None = None,
        complexity: float | None = None,
        generation: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> GenericCandidate:
        """Create a candidate from an expression string.

        Parameters
        ----------
        expression : str
            The strategy expression string
        fitness : float, optional
            Fitness/score value
        complexity : float, optional
            Complexity measure
        generation : int
            Generation/iteration number
        metadata : dict, optional
            Additional metadata

        Returns
        -------
        GenericCandidate
            The created candidate
        """
        return GenericCandidate(
            expression=expression,
            metadata=metadata or {},
            fitness=fitness if fitness is not None else self.default_fitness,
            complexity=complexity if complexity is not None else self.default_complexity,
            generation=generation,
            source_engine=self.engine_name,
        )

    def from_dict(
        self,
        data: dict[str, Any],
        *,
        expression_key: str = "expression",
        fitness_key: str = "fitness",
        complexity_key: str = "complexity",
        generation_key: str = "generation",
        id_key: str | None = "id",
    ) -> GenericCandidate:
        """Create a candidate from a dictionary.

        Parameters
        ----------
        data : dict
            Dictionary containing candidate data
        expression_key : str
            Key for the expression field
        fitness_key : str
            Key for the fitness field
        complexity_key : str
            Key for the complexity field
        generation_key : str
            Key for the generation field
        id_key : str, optional
            Key for the ID field (if None, ID is auto-generated)

        Returns
        -------
        GenericCandidate
            The created candidate
        """
        metadata = {k: v for k, v in data.items() if k not in {
            expression_key, fitness_key, complexity_key, generation_key
        }}

        if id_key and id_key in data:
            metadata["id"] = data[id_key]

        return GenericCandidate(
            expression=str(data.get(expression_key, "")),
            metadata=metadata,
            fitness=float(data.get(fitness_key, self.default_fitness)),
            complexity=float(data.get(complexity_key, self.default_complexity)),
            generation=int(data.get(generation_key, 0)),
            source_engine=self.engine_name,
            raw_data=data,
        )

    def from_dict_list(
        self,
        data_list: Sequence[dict[str, Any]],
        *,
        expression_key: str = "expression",
        fitness_key: str = "fitness",
        complexity_key: str = "complexity",
        generation_key: str = "generation",
        id_key: str | None = "id",
    ) -> list[GenericCandidate]:
        """Create candidates from a list of dictionaries.

        Parameters
        ----------
        data_list : Sequence[dict]
            List of dictionaries containing candidate data
        expression_key : str
            Key for the expression field
        fitness_key : str
            Key for the fitness field
        complexity_key : str
            Key for the complexity field
        generation_key : str
            Key for the generation field
        id_key : str, optional
            Key for the ID field

        Returns
        -------
        list[GenericCandidate]
            List of created candidates
        """
        return [
            self.from_dict(
                data,
                expression_key=expression_key,
                fitness_key=fitness_key,
                complexity_key=complexity_key,
                generation_key=generation_key,
                id_key=id_key,
            )
            for data in data_list
        ]

    def from_tuples(
        self,
        tuples: Sequence[tuple[str, float]],
        *,
        generation: int = 0,
    ) -> list[GenericCandidate]:
        """Create candidates from (expression, fitness) tuples.

        Parameters
        ----------
        tuples : Sequence[tuple[str, float]]
            List of (expression, fitness) tuples
        generation : int
            Generation number to assign to all candidates

        Returns
        -------
        list[GenericCandidate]
            List of created candidates
        """
        return [
            self.from_expression(expr, fitness=fit, generation=generation)
            for expr, fit in tuples
        ]

    def from_custom(
        self,
        items: Sequence[Any],
        extractor: Callable[[Any], dict[str, Any]],
    ) -> list[GenericCandidate]:
        """Create candidates using a custom extractor function.

        Parameters
        ----------
        items : Sequence[Any]
            List of items from the SR engine
        extractor : Callable
            Function that takes an item and returns a dict with keys:
            'expression', 'fitness', 'complexity', 'generation', 'metadata'

        Returns
        -------
        list[GenericCandidate]
            List of created candidates
        """
        candidates = []
        for item in items:
            extracted = extractor(item)
            candidates.append(
                GenericCandidate(
                    expression=str(extracted.get("expression", "")),
                    metadata=extracted.get("metadata", {}),
                    fitness=float(extracted.get("fitness", self.default_fitness)),
                    complexity=float(extracted.get("complexity", self.default_complexity)),
                    generation=int(extracted.get("generation", 0)),
                    source_engine=self.engine_name,
                    raw_data={"original": item},
                )
            )
        return candidates
