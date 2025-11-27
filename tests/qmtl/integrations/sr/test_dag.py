"""Tests for qmtl.integrations.sr.dag module."""

import pytest
import sympy as sp

from qmtl.integrations.sr.dag import (
    ExpressionDagBuilder,
    ExpressionDagSpec,
    _DagBuilder,
    _expression_key,
    build_expression_dag,
)


class TestDagBuilder:
    """Tests for the internal runtime-aware DAG builder."""

    def test_walk_symbol_and_number(self):
        builder = _DagBuilder()

        x = sp.Symbol("x")
        const = sp.Float(3.14)

        xid = builder.walk(x)
        cid = builder.walk(const)

        assert xid == "n0"
        assert cid == "n1"
        assert builder.nodes[0]["node_type"] == "input"
        assert builder.nodes[0]["params"] == {"field": "x"}
        assert builder.nodes[1]["node_type"] == "const"
        assert builder.nodes[1]["params"] == {"value": 3.14}
        assert builder.edges == []

    def test_walk_add_expression_creates_edges(self):
        builder = _DagBuilder()
        x, y = sp.symbols("x y")

        output = builder.walk(x + y)

        assert output == "n2"
        assert builder.nodes[-1]["node_type"] == "math/add"
        assert builder.nodes[-1]["inputs"] == ["n0", "n1"]
        assert set(builder.edges) == {("n0", "n2"), ("n1", "n2")}

    def test_detects_sub_and_division(self):
        builder = _DagBuilder()
        x, y = sp.symbols("x y")

        sub_output = builder.walk(x - y)
        div_output = builder.walk(x / y)

        sub_node = next(node for node in builder.nodes if node["id"] == sub_output)
        div_node = next(node for node in builder.nodes if node["id"] == div_output)

        assert sub_node["node_type"] == "math/sub"
        assert div_node["node_type"] == "math/div"

    def test_indicator_mapping(self):
        builder = _DagBuilder()
        x = sp.Symbol("price")
        expr = sp.Function("EMA")(x, 10)

        output = builder.walk(expr)
        indicator = next(node for node in builder.nodes if node["id"] == output)

        assert indicator["node_type"] == "indicator/ema"
        assert indicator["params"] == {"period": 10.0}
        assert indicator["inputs"] == ["n0"]

    def test_unsupported_function_raises(self):
        builder = _DagBuilder()
        x = sp.Symbol("x")
        expr = sp.Function("UNKNOWN")(x)

        with pytest.raises(ValueError):
            builder.walk(expr)


class TestExpressionKey:
    """Tests for _expression_key function."""

    def test_equivalent_expressions_share_key(self):
        x, y = sp.symbols("x y")
        expr1 = x + y + 0
        expr2 = y + x

        assert _expression_key(expr1) == _expression_key(expr2)

    def test_key_changes_with_expression(self):
        x, y = sp.symbols("x y")
        assert _expression_key(x + y) != _expression_key(x * y)

    def test_key_is_hex_string(self):
        key = _expression_key(sp.Symbol("x"))
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


class TestBuildExpressionDag:
    """Tests for build_expression_dag function."""

    def test_simple_expression(self):
        x = sp.Symbol("x")
        spec = build_expression_dag(
            x,
            equation="x",
            complexity=1,
            loss=0.5,
        )

        assert isinstance(spec, ExpressionDagSpec)
        assert spec.nodes[0]["node_type"] == "input"
        assert spec.output == "n0"
        assert spec.edges == []
        assert spec.equation == "x"
        assert spec.complexity == 1
        assert spec.loss == 0.5
        assert spec.node_count == 1

    def test_add_expression_builds_runtime_nodes(self):
        x, y = sp.symbols("x y")
        spec = build_expression_dag(
            x + y,
            equation="x + y",
            complexity=3,
            loss=0.1,
        )

        node_types = {node["node_type"] for node in spec.nodes}
        assert {"input", "math/add"}.issubset(node_types)
        assert spec.node_count == len(spec.nodes)
        assert spec.output in {node["id"] for node in spec.nodes}

    def test_complexity_and_loss_conversion(self):
        x = sp.Symbol("x")
        spec = build_expression_dag(
            x,
            equation="x",
            complexity="5",  # String should be converted
            loss="0.123",  # String should be converted
        )

        assert spec.complexity == 5
        assert spec.loss == 0.123
        assert isinstance(spec.complexity, int)
        assert isinstance(spec.loss, float)


class TestExpressionDagSpec:
    """Tests for ExpressionDagSpec dataclass."""

    def test_create(self):
        spec = ExpressionDagSpec(
            nodes=[{"id": "n0", "label": "input:x", "node_type": "input"}],
            edges=[],
            output="n0",
            expression_key="abc123",
            equation="x",
            complexity=1,
            loss=0.5,
            node_count=1,
            spec_version="v1",
            data_spec={"dataset_id": "foo"},
        )

        assert spec.nodes[0]["node_type"] == "input"
        assert spec.edges == []
        assert spec.output == "n0"
        assert spec.expression_key == "abc123"
        assert spec.equation == "x"
        assert spec.complexity == 1
        assert spec.loss == 0.5
        assert spec.node_count == 1
        assert spec.spec_version == "v1"
        assert spec.data_spec == {"dataset_id": "foo"}


class TestExpressionDagBuilder:
    """Tests for ExpressionDagBuilder."""

    def test_build_with_data_spec_and_version(self):
        builder = ExpressionDagBuilder(spec_version="v2")
        spec = builder.build(
            "x + y",
            complexity=3,
            loss=0.1,
            data_spec={"interval": "1m"},
        )

        assert len(spec.expression_key) == 64
        assert spec.spec_version == "v2"
        assert spec.data_spec == {"interval": "1m"}
        assert spec.node_count == len(spec.nodes)

    def test_expression_key_changes_with_version(self):
        expr = "x + y"
        key_v1 = ExpressionDagBuilder(spec_version="v1").build(expr).expression_key
        key_v2 = ExpressionDagBuilder(spec_version="v2").build(expr).expression_key

        assert key_v1 != key_v2

    def test_equation_defaults_to_normalized(self):
        builder = ExpressionDagBuilder()
        spec = builder.build("x + 0")

        assert spec.equation == "x"


class TestRealWorldExpressions:
    """Tests with real-world-like expressions."""

    def test_polynomial(self):
        x = sp.Symbol("x")
        expr = 2 * x**2 + 3 * x + 1
        spec = build_expression_dag(
            expr,
            equation="2*x**2 + 3*x + 1",
            complexity=7,
            loss=0.01,
        )

        assert spec.node_count > 1
        assert spec.complexity == 7

    def test_trigonometric(self):
        x = sp.Symbol("x")
        expr = sp.sin(x) + sp.cos(x)
        spec = build_expression_dag(
            expr,
            equation="sin(x) + cos(x)",
            complexity=5,
            loss=0.05,
        )

        node_types = {node["node_type"] for node in spec.nodes}
        assert "math/add" in node_types
        assert "math/sin" in node_types
        assert "math/cos" in node_types

    def test_nested_expression(self):
        x, y = sp.symbols("x y")
        expr = sp.exp(sp.log(x + y) * 2)
        spec = build_expression_dag(
            expr,
            equation="exp(log(x + y) * 2)",
            complexity=8,
            loss=0.02,
        )

        assert spec.node_count >= 3
