from strategies.nodes.indicators.composite_alpha import composite_alpha_node
from strategies.nodes.generators.all_alpha import all_alpha_generator_node


def test_composite_alpha_returns_mean_alpha():
    data = all_alpha_generator_node()
    result = composite_alpha_node(data)
    components = result["components"]
    expected = sum(components.values()) / len(components)
    assert result["alpha"] == expected
