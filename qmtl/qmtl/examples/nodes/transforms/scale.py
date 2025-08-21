"""Example scale transform node."""

# Source: docs/alphadocs/basic_sequence_pipeline.md

TAGS = {
    "scope": "transform",
    "family": "scale_example",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms import scale_transform_node


def scale_example_node(data: dict) -> dict:
    """Apply scale transform to metric with optional factor."""
    metric = data.get("metric", {})
    factor = data.get("factor", 2.0)
    return {"scaled": scale_transform_node(metric, factor)}

