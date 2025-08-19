from qmtl.transforms import scale_transform_node


def test_scale_transform_node_scales_metric():
    """Verify scaling of a metric by a constant factor."""
    metric = {"average": 2}
    assert scale_transform_node(metric, factor=3) == 6
