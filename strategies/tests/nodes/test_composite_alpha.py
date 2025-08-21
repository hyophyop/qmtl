import ast
import inspect
from pathlib import Path

from strategies.nodes.indicators.composite_alpha import composite_alpha_node


def _expected_component_keys() -> set[str]:
    """Extract expected component keys from composite_alpha implementation."""
    source = Path(inspect.getfile(composite_alpha_node)).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and key.value == "components":
                    if isinstance(value, ast.Dict):
                        return {
                            k.value for k in value.keys if isinstance(k, ast.Constant)
                        }
    raise AssertionError("components dictionary not found")


def _input_keys() -> set[str]:
    """Extract expected input keys from composite_alpha implementation."""
    source = Path(inspect.getfile(composite_alpha_node)).read_text()
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "data"
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


def test_composite_alpha_returns_mean_alpha():
    """Test that composite alpha correctly computes mean of all components."""
    data = {}
    result = composite_alpha_node(data)
    components = result["components"]
    expected = sum(components.values()) / len(components)
    assert result["alpha"] == expected

    assert set(components.keys()) == _expected_component_keys()


def test_composite_alpha_with_sample_data():
    """Test composite alpha with dynamically generated input data."""
    data = {key: {} for key in _input_keys()}
    result = composite_alpha_node(data)
    components = result["components"]
    expected = sum(components.values()) / len(components)
    assert result["alpha"] == expected
    assert set(components.keys()) == _expected_component_keys()

