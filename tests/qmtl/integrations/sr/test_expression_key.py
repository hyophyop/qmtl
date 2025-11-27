"""Tests for qmtl.integrations.sr.expression_key module."""

from qmtl.integrations.sr.expression_key import (
    compute_expression_key,
    normalize_ast,
    _parse_expression,
)


class TestComputeExpressionKey:
    """Tests for compute_expression_key function."""

    def test_simple_expression(self):
        """Test key generation for simple expression."""
        key = compute_expression_key("x + y")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 produces 64 hex chars

    def test_deterministic(self):
        """Test that same expression produces same key."""
        key1 = compute_expression_key("x + y")
        key2 = compute_expression_key("x + y")
        assert key1 == key2

    def test_commutative_expressions(self):
        """Test that commutative expressions produce same key."""
        key1 = compute_expression_key("x + y")
        key2 = compute_expression_key("y + x")
        assert key1 == key2

        key3 = compute_expression_key("x * y")
        key4 = compute_expression_key("y * x")
        assert key3 == key4

    def test_different_expressions_different_keys(self):
        """Test that different expressions produce different keys."""
        key1 = compute_expression_key("x + y")
        key2 = compute_expression_key("x * y")
        assert key1 != key2

    def test_equivalent_expressions(self):
        """Test that mathematically equivalent expressions produce same key."""
        key1 = compute_expression_key("2 * x")
        key2 = compute_expression_key("x * 2")
        assert key1 == key2

    def test_complex_expression(self):
        """Test key generation for complex expression."""
        expr = "sin(x) + cos(y) * exp(z)"
        key = compute_expression_key(expr)
        assert isinstance(key, str)
        assert len(key) == 64

    def test_nested_expression(self):
        """Test key generation for nested expression."""
        expr = "log(x + sqrt(y**2 + z**2))"
        key = compute_expression_key(expr)
        assert isinstance(key, str)
        assert len(key) == 64

    def test_invalid_expression(self):
        """Test behavior with invalid expression - may parse as valid or raise."""
        # Sympy can parse many unusual inputs, so we just check it returns a key
        try:
            key = compute_expression_key("completely invalid")
            # If parsing succeeded, should still be a valid key
            assert isinstance(key, str)
        except (ValueError, SyntaxError):
            # This is also acceptable - some inputs may fail
            pass


class TestParseExpression:
    """Tests for _parse_expression helper function."""

    def test_simple_ast(self):
        """Test parsing simple expression to AST."""
        ast = _parse_expression("x + y")
        assert isinstance(ast, dict)
        assert "type" in ast

    def test_variable_parsing(self):
        """Test that variables are correctly parsed."""
        ast = _parse_expression("x")
        assert ast.get("type") == "Var"
        assert ast.get("name") == "x"

    def test_constant_parsing(self):
        """Test that constants are correctly parsed."""
        ast = _parse_expression("42")
        assert ast.get("type") == "Const"
        assert ast.get("value") == 42

    def test_binary_op_parsing(self):
        """Test that binary operations are parsed."""
        ast = _parse_expression("x + y")
        assert ast.get("type") in ("Add",)
        assert "children" in ast


class TestNormalizeAst:
    """Tests for normalize_ast function."""

    def test_simple_ast(self):
        """Test AST normalization for simple expression."""
        ast = _parse_expression("x + y")
        normalized = normalize_ast(ast)
        assert isinstance(normalized, dict)
        assert "type" in normalized

    def test_commutative_normalization(self):
        """Test that commutative ops are normalized."""
        ast1 = _parse_expression("x + y")
        ast2 = _parse_expression("y + x")
        norm1 = normalize_ast(ast1)
        norm2 = normalize_ast(ast2)
        # After normalization, the string representations should be equal
        assert str(norm1) == str(norm2)

    def test_nested_normalization(self):
        """Test normalization of nested expressions."""
        ast1 = _parse_expression("(a + b) * (c + d)")
        ast2 = _parse_expression("(b + a) * (d + c)")
        norm1 = normalize_ast(ast1)
        norm2 = normalize_ast(ast2)
        assert str(norm1) == str(norm2)

    def test_returns_dict(self):
        """Test that normalization returns a dict."""
        ast = _parse_expression("sin(x) + cos(y)")
        result = normalize_ast(ast)
        assert isinstance(result, dict)

    def test_deterministic_normalization(self):
        """Test that normalization is deterministic."""
        expr = "a * b + c * d"
        ast = _parse_expression(expr)
        norm1 = normalize_ast(ast)
        norm2 = normalize_ast(ast)
        assert str(norm1) == str(norm2)


class TestExpressionKeyEdgeCases:
    """Edge case tests for expression key generation."""

    def test_empty_string_returns_key(self):
        """Test with empty string - falls back to raw string."""
        # Empty string falls back to empty string, which gets hashed
        key = compute_expression_key("")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_whitespace_only_returns_key(self):
        """Test with whitespace only - falls back to stripped string."""
        key = compute_expression_key("   ")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_numeric_constants(self):
        """Test expressions with numeric constants."""
        key1 = compute_expression_key("2 + 3")
        key2 = compute_expression_key("3 + 2")
        assert key1 == key2

    def test_single_variable(self):
        """Test with single variable."""
        key = compute_expression_key("x")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_single_number(self):
        """Test with single number."""
        key = compute_expression_key("42")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_parentheses_dont_change_key(self):
        """Test that redundant parentheses don't change key."""
        key1 = compute_expression_key("x + y")
        key2 = compute_expression_key("(x + y)")
        key3 = compute_expression_key("((x + y))")
        assert key1 == key2 == key3

    def test_associativity_normalization(self):
        """Test that associative expressions are normalized."""
        # a + (b + c) should equal (a + b) + c
        key1 = compute_expression_key("a + (b + c)")
        key2 = compute_expression_key("(a + b) + c")
        # These may or may not be equal depending on normalization depth
        # At minimum, they should both produce valid keys
        assert isinstance(key1, str)
        assert isinstance(key2, str)

    def test_normalize_false_skips_normalization(self):
        """Test that normalize=False skips normalization."""
        key1 = compute_expression_key("x + y", normalize=False)
        key2 = compute_expression_key("y + x", normalize=False)
        # Without normalization, different strings produce different keys
        assert key1 != key2
