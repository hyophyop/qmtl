from qmtl.runtime.transforms import scale_transform_node


def test_scale_transform_node_scales_average():
    metric = {"average": 4}
    assert scale_transform_node(metric, factor=0.5) == 2
