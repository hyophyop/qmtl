from qmtl.examples.nodes.indicators import average_indicator_node


def test_average_indicator_node_computes_mean():
    """Check that the average indicator computes the mean of numbers."""
    data = {"numbers": [1, 2, 3]}
    assert average_indicator_node(data) == {"average": 2}
