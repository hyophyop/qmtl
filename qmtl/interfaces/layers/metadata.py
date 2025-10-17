"""Layer metadata definitions and loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class Layer(str, Enum):
    """Available strategy layers."""

    DATA = "data"
    SIGNAL = "signal"
    EXECUTION = "execution"
    BROKERAGE = "brokerage"
    MONITORING = "monitoring"


# Layer dependency graph
LAYER_DEPENDENCIES: Dict[Layer, List[Layer]] = {
    Layer.DATA: [],
    Layer.SIGNAL: [Layer.DATA],
    Layer.EXECUTION: [Layer.SIGNAL],
    Layer.BROKERAGE: [Layer.EXECUTION],
    Layer.MONITORING: [],  # Independent - can work with any layer
}


@dataclass
class TemplateInfo:
    """Information about a layer template."""

    name: str
    file: str
    description: str
    complexity: str = "beginner"  # beginner, intermediate, advanced
    requires: List[str] = field(default_factory=list)  # Python package dependencies


@dataclass
class LayerMetadata:
    """Metadata for a strategy layer."""

    layer: Layer
    description: str
    dependencies: List[Layer] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)  # What components this layer provides
    templates: List[TemplateInfo] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LayerMetadata:
        """Load metadata from dictionary."""
        layer = Layer(data["layer"])
        dependencies = [Layer(d) for d in data.get("dependencies", [])]
        templates = [
            TemplateInfo(
                name=t["name"],
                file=t["file"],
                description=t["description"],
                complexity=t.get("complexity", "beginner"),
                requires=t.get("requires", []),
            )
            for t in data.get("templates", [])
        ]
        return cls(
            layer=layer,
            description=data["description"],
            dependencies=dependencies,
            provides=data.get("provides", []),
            templates=templates,
        )


def load_layer_metadata(layer: Layer) -> LayerMetadata:
    """Load metadata for a specific layer.

    This is a stub implementation. In a full implementation, this would
    load from YAML files in the templates/layers directory.
    """
    # Default metadata for each layer
    metadata_map = {
        Layer.DATA: LayerMetadata(
            layer=Layer.DATA,
            description="Data ingestion and streaming layer",
            dependencies=[],
            provides=["StreamInput", "HistoryProvider", "DataProvider"],
            templates=[
                TemplateInfo(
                    name="stream_input",
                    file="stream_input.py",
                    description="Basic StreamInput with configurable interval",
                    complexity="beginner",
                ),
                TemplateInfo(
                    name="ccxt_provider",
                    file="ccxt_provider.py",
                    description="CCXT-based data provider for exchange data",
                    complexity="intermediate",
                    requires=["ccxt"],
                ),
            ],
        ),
        Layer.SIGNAL: LayerMetadata(
            layer=Layer.SIGNAL,
            description="Signal generation and alpha computation layer",
            dependencies=[Layer.DATA],
            provides=["Indicators", "Transforms", "Alpha"],
            templates=[
                TemplateInfo(
                    name="single_indicator",
                    file="single_indicator.py",
                    description="Single indicator strategy",
                    complexity="beginner",
                ),
                TemplateInfo(
                    name="multi_indicator",
                    file="multi_indicator.py",
                    description="Multiple indicator strategy",
                    complexity="intermediate",
                ),
            ],
        ),
        Layer.EXECUTION: LayerMetadata(
            layer=Layer.EXECUTION,
            description="Order execution and management layer",
            dependencies=[Layer.SIGNAL],
            provides=["PreTradeGate", "Sizing", "ExecutionNode"],
            templates=[
                TemplateInfo(
                    name="nodeset",
                    file="nodeset.py",
                    description="NodeSet-based execution pipeline",
                    complexity="intermediate",
                ),
            ],
        ),
        Layer.BROKERAGE: LayerMetadata(
            layer=Layer.BROKERAGE,
            description="Brokerage integration layer",
            dependencies=[Layer.EXECUTION],
            provides=["CCXT", "IBKR", "BrokerageConnector"],
            templates=[
                TemplateInfo(
                    name="ccxt_binance",
                    file="ccxt_binance.py",
                    description="Binance integration via CCXT",
                    complexity="intermediate",
                    requires=["ccxt"],
                ),
            ],
        ),
        Layer.MONITORING: LayerMetadata(
            layer=Layer.MONITORING,
            description="Monitoring and metrics collection layer",
            dependencies=[],
            provides=["Metrics", "EventRecorder", "Logging"],
            templates=[
                TemplateInfo(
                    name="metrics",
                    file="metrics.py",
                    description="Basic metrics collection",
                    complexity="beginner",
                ),
            ],
        ),
    }
    return metadata_map[layer]


def get_all_layers() -> List[Layer]:
    """Get all available layers."""
    return list(Layer)


def get_layer_dependencies(layer: Layer) -> List[Layer]:
    """Get direct dependencies for a layer."""
    return LAYER_DEPENDENCIES.get(layer, [])


def get_transitive_dependencies(layer: Layer) -> List[Layer]:
    """Get all transitive dependencies for a layer."""
    result = []
    to_process = [layer]
    seen = set()

    while to_process:
        current = to_process.pop(0)
        if current in seen:
            continue
        seen.add(current)

        deps = get_layer_dependencies(current)
        result.extend(deps)
        to_process.extend(deps)

    # Remove duplicates and maintain order
    unique_result = []
    for item in result:
        if item not in unique_result:
            unique_result.append(item)

    return unique_result
