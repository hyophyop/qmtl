"""Layer-based project scaffolding system.

This module provides a composable layer system for creating QMTL projects.
Each layer represents a distinct concern (data, signal, execution, etc.) and
can be independently combined to create custom project structures.
"""

from __future__ import annotations

from .metadata import (
    Layer,
    LayerMetadata,
    load_layer_metadata,
    get_layer_dependencies,
    get_transitive_dependencies,
    get_all_layers,
)
from .validator import LayerValidator, ValidationResult
from .composer import LayerComposer
from .preset import PresetConfig, PresetLoader

__all__ = [
    "Layer",
    "LayerMetadata",
    "load_layer_metadata",
    "get_layer_dependencies",
    "get_transitive_dependencies",
    "get_all_layers",
    "LayerValidator",
    "ValidationResult",
    "LayerComposer",
    "PresetConfig",
    "PresetLoader",
]
