"""Layer combination validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from .metadata import Layer, get_layer_dependencies, get_transitive_dependencies


@dataclass
class ValidationResult:
    """Result of layer validation."""

    valid: bool
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class LayerValidator:
    """Validates layer combinations and dependencies."""

    def validate_layers(self, layers: List[Layer]) -> ValidationResult:
        """Validate a list of layers for correctness.

        Checks:
        1. All dependencies are satisfied
        2. No circular dependencies (should be impossible by design)
        3. No duplicate layers
        """
        result = ValidationResult(valid=True)

        # Check for duplicates
        if len(layers) != len(set(layers)):
            duplicates = [layer for layer in layers if layers.count(layer) > 1]
            result.valid = False
            result.errors.append(f"Duplicate layers found: {duplicates}")
            return result

        # Check dependencies
        layer_set = set(layers)
        for layer in layers:
            deps = get_layer_dependencies(layer)
            missing_deps = set(deps) - layer_set

            if missing_deps:
                result.valid = False
                result.errors.append(
                    f"Layer '{layer.value}' requires missing dependencies: "
                    f"{[d.value for d in missing_deps]}"
                )

        return result

    def validate_add_layer(
        self, existing_layers: List[Layer], new_layer: Layer
    ) -> ValidationResult:
        """Validate adding a new layer to existing layers.

        Returns validation result indicating if the addition is valid.
        """
        result = ValidationResult(valid=True)

        # Check if layer already exists
        if new_layer in existing_layers:
            result.valid = False
            result.errors.append(
                f"Layer '{new_layer.value}' already exists. "
                "Use --force to replace."
            )
            return result

        # Check if dependencies are satisfied
        deps = get_layer_dependencies(new_layer)
        existing_set = set(existing_layers)
        missing_deps = set(deps) - existing_set

        if missing_deps:
            result.valid = False
            result.errors.append(
                f"Layer '{new_layer.value}' requires missing dependencies: "
                f"{[d.value for d in missing_deps]}"
            )
            # Provide helpful suggestion
            result.errors.append(
                f"Add the following layers first: {[d.value for d in missing_deps]}"
            )

        return result

    def get_minimal_layer_set(self, target_layers: List[Layer]) -> List[Layer]:
        """Get minimal set of layers including all transitive dependencies.

        Given a list of desired layers, returns the complete list including
        all required dependencies, ordered by dependency.
        """
        all_layers: Set[Layer] = set()

        # Collect all layers and their transitive dependencies
        for layer in target_layers:
            all_layers.add(layer)
            all_layers.update(get_transitive_dependencies(layer))

        # Sort by dependency order
        return self._topological_sort(list(all_layers))

    def _topological_sort(self, layers: List[Layer]) -> List[Layer]:
        """Sort layers by dependency order (dependencies first)."""
        sorted_layers = []
        remaining = set(layers)

        while remaining:
            # Find layers with no unsatisfied dependencies in remaining set
            ready = [
                layer
                for layer in remaining
                if all(dep not in remaining for dep in get_layer_dependencies(layer))
            ]

            if not ready:
                # Should never happen with a valid dependency graph
                raise ValueError("Circular dependency detected")

            # Add ready layers to result
            sorted_layers.extend(sorted(ready, key=lambda x: x.value))
            remaining -= set(ready)

        return sorted_layers

    def suggest_layers_for_use_case(self, use_case: str) -> List[Layer]:
        """Suggest appropriate layers for a given use case.

        Args:
            use_case: One of 'backtest', 'research', 'production', 'execution'

        Returns:
            List of recommended layers
        """
        use_case_map = {
            "backtest": [Layer.DATA, Layer.SIGNAL],
            "research": [Layer.DATA, Layer.SIGNAL, Layer.MONITORING],
            "production": [
                Layer.DATA,
                Layer.SIGNAL,
                Layer.EXECUTION,
                Layer.BROKERAGE,
                Layer.MONITORING,
            ],
            "execution": [Layer.EXECUTION, Layer.BROKERAGE],
        }

        layers = use_case_map.get(use_case.lower(), [])
        return self.get_minimal_layer_set(layers)
