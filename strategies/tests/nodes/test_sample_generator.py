from strategies.nodes.generators import sample_generator


def test_sample_generator_returns_value_42():
    """Ensure sample_generator returns the expected payload."""
    assert sample_generator() == {"value": 42}
