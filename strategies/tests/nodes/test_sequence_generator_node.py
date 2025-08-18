from strategies.nodes.generators import sequence_generator_node
from strategies.nodes.generators.sequence import TAGS


def test_sequence_generator_node_returns_numbers():
    """Ensure the sequence generator returns a fixed set of numbers."""
    assert sequence_generator_node() == {"numbers": [1, 2, 3]}


def test_sequence_generator_node_scope_is_generator():
    """Ensure the sequence generator is tagged correctly."""
    assert TAGS["scope"] == "generator"
