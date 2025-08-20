"""Scale transform node example."""

# Source: docs/alphadocs/basic_sequence_pipeline.md

TAGS = {
    "scope": "transform",
    "family": "scale",
    "interval": "1d",
    "asset": "sample",
}


def scale_transform_node(metric: dict, factor: float = 2.0) -> float:
    """Return the ``average`` metric scaled by ``factor``."""
    return metric["average"] * factor