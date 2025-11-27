"""Tests for qmtl.integrations.sr.dag module."""

import sympy as sp

from qmtl.integrations.sr.dag import (
    ExpressionDagSpec,
    ExpressionDagBuilder,
    build_expression_dag,
    _DagBuilder,
    _expression_key,
)


class TestDagBuilder:
    """Tests for _DagBuilder internal class."""

    def test_walk_symbol(self):
        """Test walking a symbol node."""
        builder = _DagBuilder()
        x = sp.Symbol("x")
        nid = builder.walk(x)

        assert nid == "n0"
        assert len(builder.nodes) == 1
        assert builder.nodes[0]["label"] == "var:x"
        assert builder.edges == []

    def test_walk_number(self):
        """Test walking a number node."""
        builder = _DagBuilder()
        num = sp.Float(3.14)
        nid = builder.walk(num)

        assert nid == "n0"
        assert len(builder.nodes) == 1
        assert builder.nodes[0]["label"] == "const:3.14"

    def test_walk_integer(self):
        """Test walking an integer node."""
        builder = _DagBuilder()
        num = sp.Integer(42)
        nid = builder.walk(num)

        assert nid == "n0"
        assert len(builder.nodes) == 1
        assert builder.nodes[0]["label"] == "const:42.0"

    def test_walk_add_expression(self):
        """Test walking an addition expression."""
        builder = _DagBuilder()
        x, y = sp.symbols("x y")
        expr = x + y
        builder.walk(expr)

        # x + y creates nodes for each operand and the Add operation
        assert len(builder.nodes) == 3
        # Check that we have the expected node types
        labels = [n["label"] for n in builder.nodes]
        assert any("op:Add" in label for label in labels)
        assert any("var:x" in label for label in labels)
        assert any("var:y" in label for label in labels)
        assert len(builder.edges) == 2  # x->Add, y->Add

    def test_walk_complex_expression(self):
        """Test walking a complex nested expression."""
        builder = _DagBuilder()
        x, y, z = sp.symbols("x y z")
        expr = (x + y) * z
        builder.walk(expr)

        # Creates: var:x, var:y, op:Add, var:z, op:Mul
        assert len(builder.nodes) == 5
        # Edges: x->Add, y->Add, Add->Mul, z->Mul
        assert len(builder.edges) == 4


class TestExpressionKey:
    """Tests for _expression_key function."""

    def test_same_expression_same_key(self):
        """Test that same expressions produce same keys."""
        x, y = sp.symbols("x y")
        expr1 = x + y
        expr2 = x + y

        key1 = _expression_key(expr1)
        key2 = _expression_key(expr2)

        assert key1 == key2

    def test_different_expression_different_key(self):
        """Test that different expressions produce different keys."""
        x, y = sp.symbols("x y")
        expr1 = x + y
        expr2 = x * y

        key1 = _expression_key(expr1)
        key2 = _expression_key(expr2)

        assert key1 != key2

    def test_key_is_hex_string(self):
        """Test that key is a valid hex string."""
        x = sp.Symbol("x")
        key = _expression_key(x)

        assert len(key) == 64  # SHA256 hex
        assert all(c in "0123456789abcdef" for c in key)


class TestBuildExpressionDag:
    """Tests for build_expression_dag function."""

    def test_simple_expression(self):
        """Test building DAG from simple expression."""
        x = sp.Symbol("x")
        spec = build_expression_dag(
            x,
            equation="x",
            complexity=1,
            loss=0.5,
        )

        assert isinstance(spec, ExpressionDagSpec)
        assert len(spec.nodes) == 1
        assert spec.nodes[0]["label"] == "var:x"
        assert spec.edges == []
        assert spec.equation == "x"
        assert spec.complexity == 1
        assert spec.loss == 0.5
        assert spec.node_count == 1

    def test_binary_expression(self):
        """Test building DAG from binary expression."""
        x, y = sp.symbols("x y")
        expr = x + y
        spec = build_expression_dag(
            expr,
            equation="x + y",
            complexity=3,
            loss=0.1,
        )

        assert spec.node_count == 3
        assert len(spec.edges) == 2
        # Output node should exist
        assert spec.output in [n["id"] for n in spec.nodes]

    def test_expression_key_is_set(self):
        """Test that expression_key is properly set."""
        x = sp.Symbol("x")
        spec = build_expression_dag(
            x,
            equation="x",
            complexity=1,
            loss=0.5,
        )

        assert spec.expression_key is not None
        assert len(spec.expression_key) == 64

    def test_complexity_and_loss_conversion(self):
        """Test that complexity and loss are properly converted."""
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
        """Test creating ExpressionDagSpec."""
        spec = ExpressionDagSpec(
            nodes=[{"id": "n0", "label": "var:x"}],
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

        assert spec.nodes == [{"id": "n0", "label": "var:x"}]
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
        spec = builder.build("x + y", complexity=3, loss=0.1, data_spec={"interval": "1m"})

        assert len(spec.expression_key) == 64
        assert spec.spec_version == "v2"
        assert spec.data_spec == {"interval": "1m"}
        assert spec.node_count == len(spec.nodes)

    def test_expression_key_changes_with_version(self):
        expr = "x + y"
        key_v1 = ExpressionDagBuilder(spec_version="v1").build(expr).expression_key
        key_v2 = ExpressionDagBuilder(spec_version="v2").build(expr).expression_key

        assert key_v1 != key_v2


class TestRealWorldExpressions:
    """Tests with real-world-like expressions."""

    def test_polynomial(self):
        """Test polynomial expression."""
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
        """Test trigonometric expression."""
        x = sp.Symbol("x")
        expr = sp.sin(x) + sp.cos(x)
        spec = build_expression_dag(
            expr,
            equation="sin(x) + cos(x)",
            complexity=5,
            loss=0.05,
        )

        # sin(x) + cos(x) -> var:x, op:sin, op:cos, op:Add
        # Note: sympy may reuse x node
        assert spec.node_count >= 3

    def test_nested_expression(self):
        """Test deeply nested expression."""
        x, y = sp.symbols("x y")
        expr = sp.exp(sp.log(x + y) * 2)
        spec = build_expression_dag(
            expr,
            equation="exp(log(x + y) * 2)",
            complexity=8,
            loss=0.02,
        )

        # Sympy may simplify exp(log(...)*2) to (x+y)^2
        # Just verify we got a valid DAG with multiple nodes
        assert spec.node_count >= 3
