"""Scale the average metric."""

# Source: docs/alphadocs/basic_sequence_pipeline.md

TAGS = {
    "scope": "transform",
    "family": "scale",
    "interval": "1d",
    "asset": "sample",
}


def scale_transform_node(metric, factor=2.0):
    """Scale the average by a constant factor."""
    return metric["average"] * factor
