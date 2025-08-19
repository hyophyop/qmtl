"""Scale the average metric."""

# Source: docs/alphadocs/basic_sequence_pipeline.md


def scale_transform_node(metric: dict, factor: float = 2.0) -> float:
    """Return the ``average`` metric scaled by ``factor``."""
    return metric["average"] * factor
