from qmtl.examples.nodes.generators import sequence_generator_node


def test_sequence_generator_node_returns_numbers():
    """Ensure the sequence generator returns a fixed set of numbers."""
    assert sequence_generator_node() == {"numbers": [1, 2, 3]}
