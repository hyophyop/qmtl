"""Scale the average metric."""


def scale_transform_node(metric, factor=2.0):
    """Scale the average by a constant factor."""
    return metric["average"] * factor
