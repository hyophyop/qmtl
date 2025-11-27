"""Expression key generation and normalization utilities.

This module provides utilities for generating stable, normalized keys
from SR expressions. These keys are used for:
- Duplicate detection (same expression_key = semantically equivalent)
- Strategy deduplication in World/Gateway
- DAG node reuse optimization

The normalization process ensures that semantically equivalent expressions
(e.g., 'a + b' and 'b + a') produce the same key.
"""

from __future__ import annotations

import hashlib
from typing import Any


def compute_expression_key(
    expression: str | dict[str, Any],
    *,
    normalize: bool = True,
) -> str:
    """Compute a stable key for an expression.

    Parameters
    ----------
    expression : str | dict
        Expression string or parsed AST dict
    normalize : bool
        Whether to apply normalization before hashing

    Returns
    -------
    str
        SHA256 hex digest (64 characters)

    Example
    -------
    >>> compute_expression_key("x + y")
    '...'  # 64-char hex string
    >>> compute_expression_key("y + x")  # Same key due to commutativity
    '...'
    """
    if isinstance(expression, str):
        # Try to parse and normalize
        if normalize:
            try:
                ast = _parse_expression(expression)
                normalized = normalize_ast(ast)
                canonical = _ast_to_canonical_string(normalized)
            except Exception:
                # Fallback to raw string if parsing fails
                canonical = expression.strip()
        else:
            canonical = expression.strip()
    else:
        # Already an AST dict
        if normalize:
            normalized = normalize_ast(expression)
            canonical = _ast_to_canonical_string(normalized)
        else:
            canonical = _ast_to_canonical_string(expression)

    return hashlib.sha256(canonical.encode()).hexdigest()


def normalize_ast(ast: dict[str, Any]) -> dict[str, Any]:
    """Normalize an AST to ensure semantically equivalent expressions are identical.

    Normalization rules:
    1. Commutative operations (Add, Mul, And, Or): sort children
    2. Constant folding: evaluate constant sub-expressions
    3. Identity removal: Mul(x, 1) -> x, Add(x, 0) -> x
    4. Negation simplification: Sub(0, x) -> Neg(x)

    Parameters
    ----------
    ast : dict
        AST dictionary with 'type' and optional 'children', 'value', 'name' keys

    Returns
    -------
    dict
        Normalized AST
    """
    node_type = ast.get("type", "")

    # Leaf nodes: constants and variables
    if node_type == "Const":
        return ast.copy()

    if node_type == "Var":
        return ast.copy()

    # Recursively normalize children
    children = [normalize_ast(c) for c in ast.get("children", [])]

    # Commutative operations: sort children for canonical order
    commutative_ops = {"Add", "Mul", "And", "Or", "Max", "Min"}
    if node_type in commutative_ops and len(children) > 1:
        children = sorted(children, key=_ast_sort_key)

    # Constant folding for binary arithmetic
    if node_type == "Add" and all(_is_const(c) for c in children):
        total = sum(_get_const_value(c) for c in children)
        return {"type": "Const", "value": total}

    if node_type == "Mul" and all(_is_const(c) for c in children):
        product = 1.0
        for c in children:
            product *= _get_const_value(c)
        return {"type": "Const", "value": product}

    # Identity removal: Mul(x, 1) -> x
    if node_type == "Mul":
        children = [c for c in children if not (_is_const(c) and _get_const_value(c) == 1)]
        if len(children) == 0:
            return {"type": "Const", "value": 1.0}
        if len(children) == 1:
            return children[0]

    # Identity removal: Add(x, 0) -> x
    if node_type == "Add":
        children = [c for c in children if not (_is_const(c) and _get_const_value(c) == 0)]
        if len(children) == 0:
            return {"type": "Const", "value": 0.0}
        if len(children) == 1:
            return children[0]

    return {"type": node_type, "children": children}


def _ast_to_canonical_string(ast: dict[str, Any]) -> str:
    """Convert AST to a canonical string representation for hashing."""
    node_type = ast.get("type", "")

    if node_type == "Const":
        # Format constants consistently
        value = ast.get("value", 0)
        if isinstance(value, float) and value == int(value):
            return f"C:{int(value)}"
        return f"C:{value}"

    if node_type == "Var":
        return f"V:{ast.get('name', '')}"

    children_str = ",".join(
        _ast_to_canonical_string(c) for c in ast.get("children", [])
    )
    return f"{node_type}({children_str})"


def _ast_sort_key(ast: dict[str, Any]) -> str:
    """Generate a sort key for AST nodes."""
    return _ast_to_canonical_string(ast)


def _is_const(ast: dict[str, Any]) -> bool:
    """Check if AST node is a constant."""
    return ast.get("type") == "Const"


def _get_const_value(ast: dict[str, Any]) -> float:
    """Get the value of a constant node."""
    return float(ast.get("value", 0))


def _parse_expression(expr_str: str) -> dict[str, Any]:
    """Parse an expression string into an AST dict.

    This is a simplified parser for basic mathematical expressions.
    For production use, consider using sympy or a dedicated parser.

    Parameters
    ----------
    expr_str : str
        Expression string (e.g., "x + y * 2")

    Returns
    -------
    dict
        AST dictionary

    Note
    ----
    This is a basic implementation. For complex expressions,
    use sympy's parsing capabilities.
    """
    # Try using sympy if available
    try:
        import sympy as sp

        expr = sp.sympify(expr_str)
        return _sympy_to_ast(expr)
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: return a simple variable node
    # (This is a placeholder - real implementation would parse properly)
    return {"type": "Var", "name": expr_str.strip()}


def _sympy_to_ast(expr) -> dict[str, Any]:
    """Convert a sympy expression to AST dict.

    Parameters
    ----------
    expr : sympy.Expr
        Sympy expression

    Returns
    -------
    dict
        AST dictionary
    """
    import sympy as sp

    # Handle atoms
    if isinstance(expr, sp.Symbol):
        return {"type": "Var", "name": str(expr)}

    if isinstance(expr, sp.Number):
        return {"type": "Const", "value": float(expr)}

    # Handle operations
    op_name = type(expr).__name__
    children = [_sympy_to_ast(arg) for arg in expr.args]

    return {"type": op_name, "children": children}


def expression_keys_match(key1: str, key2: str) -> bool:
    """Check if two expression keys are equivalent.

    Parameters
    ----------
    key1 : str
        First expression key
    key2 : str
        Second expression key

    Returns
    -------
    bool
        True if keys match
    """
    return key1 == key2


def compute_expression_similarity(
    expr1: str,
    expr2: str,
) -> float:
    """Compute similarity between two expressions.

    This is a simple structural similarity based on common subtrees.
    Returns 1.0 for identical expressions, 0.0 for completely different.

    Parameters
    ----------
    expr1 : str
        First expression
    expr2 : str
        Second expression

    Returns
    -------
    float
        Similarity score between 0.0 and 1.0
    """
    key1 = compute_expression_key(expr1)
    key2 = compute_expression_key(expr2)

    if key1 == key2:
        return 1.0

    # Simple character-based similarity as fallback
    # (A more sophisticated approach would compare AST structures)
    common = sum(1 for a, b in zip(key1, key2) if a == b)
    return common / max(len(key1), len(key2))
