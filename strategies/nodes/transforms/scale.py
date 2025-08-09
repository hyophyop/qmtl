"""Scale the average metric."""

# Source: docs/alphadocs/basic_sequence_pipeline.md


def scale_transform_node(metric, factor=2.0):
    """Scale the average by a constant factor."""
    return metric["average"] * factor
