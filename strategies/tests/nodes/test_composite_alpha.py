import ast
import inspect
from pathlib import Path

import strategies.nodes.indicators.composite_alpha as composite_alpha_module
from strategies.nodes.indicators.composite_alpha import composite_alpha_node


def _expected_component_keys() -> set[str]:
    """Extract component keys from ``components`` assignment in implementation."""
    source = Path(inspect.getfile(composite_alpha_node)).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "components" for t in node.targets
            )
            and isinstance(node.value, ast.Dict)
        ):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("components dict assignment not found")


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


def test_composite_alpha_weighted_average(monkeypatch):
    """Test composite alpha with custom weights."""
    values = {
        "acceptable_price_band": 1.0,
        "gap_amplification": 2.0,
        "latent_liquidity": 3.0,
        "non_linear": 4.0,
        "order_book_clustering": 5.0,
        "quantum_echo": 6.0,
        "tactical_liquidity_bifurcation": 7.0,
        "execution_diffusion_contraction": 8.0,
        "resiliency": 9.0,
        "execution_velocity_hazard": 10.0,
    }
    monkeypatch.setattr(
        composite_alpha_module,
        "acceptable_price_band_node",
        lambda data: {"alpha": values["acceptable_price_band"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "gap_amplification_node",
        lambda data: {"alpha": values["gap_amplification"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "latent_liquidity_alpha_node",
        lambda data: {"alpha": values["latent_liquidity"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "non_linear_alpha_node",
        lambda data: {"alpha": values["non_linear"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "order_book_clustering_collapse_node",
        lambda data: {"alpha": values["order_book_clustering"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "quantum_liquidity_echo_node",
        lambda data: {"echo_amplitude": values["quantum_echo"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "tactical_liquidity_bifurcation_node",
        lambda data: {"alpha": values["tactical_liquidity_bifurcation"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "execution_diffusion_contraction_node",
        lambda data: {"alpha": values["execution_diffusion_contraction"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "resiliency_alpha_node",
        lambda data: {"alpha": values["resiliency"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "execution_velocity_hazard_node",
        lambda data: {"alpha": values["execution_velocity_hazard"]},
    )
    monkeypatch.setattr(
        composite_alpha_module,
        "llrti_node",
        lambda data: {"llrti": 0.0, "hazard_jump": 0.0, "cost": 0.0},
    )

    weights = {k: i for i, k in enumerate(values, start=1)}
    result = composite_alpha_module.composite_alpha_node({}, weights=weights)
    expected = sum(values[k] * weights[k] for k in values) / sum(weights.values())
    assert result["alpha"] == expected
    assert result["components"] == values

