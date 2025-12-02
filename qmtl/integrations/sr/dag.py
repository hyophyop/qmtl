"""Expression→DAG compilation utilities for SR integrations.

This module turns Sympy expressions into a runtime-friendly DAG spec
that references existing ``qmtl.runtime`` node types (math/logic ops and
common indicators). The builder performs a light-weight normalization so
semantically equivalent expressions share the same ``expression_key``
within a given ``spec_version``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, List, Mapping, Tuple

try:
    import sympy as sp
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("sympy is required to build expression DAGs") from exc


@dataclass
class ExpressionDagSpec:
    """Sympy expression → DAG representation."""

    nodes: List[dict]
    edges: List[Tuple[str, str]]
    output: str
    expression_key: str
    equation: str
    complexity: int
    loss: float
    node_count: int
    spec_version: str = "v1"
    data_spec: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class NodeMapping:
    """Declarative mapping from a Sympy op/func to a runtime node."""

    node_type: str
    param_names: tuple[str, ...] = ()
    input_arity: int | None = None
    label: str | None = None


_COMMUTATIVE_FUNCS = {"Add", "Mul", "And", "Or", "Max", "Min"}
_NEUTRAL_ELEMENTS = {"Add": 0, "Mul": 1}

_OPERATOR_NODE_MAP: dict[str, NodeMapping] = {
    "Add": NodeMapping("math/add", label="add"),
    "Mul": NodeMapping("math/mul", label="mul"),
    "Pow": NodeMapping("math/pow", label="pow"),
    "And": NodeMapping("logic/and", label="and"),
    "Or": NodeMapping("logic/or", label="or"),
    "Not": NodeMapping("logic/not", input_arity=1, label="not"),
    "Abs": NodeMapping("math/abs", input_arity=1, label="abs"),
    "sin": NodeMapping("math/sin", input_arity=1, label="sin"),
    "cos": NodeMapping("math/cos", input_arity=1, label="cos"),
    "exp": NodeMapping("math/exp", input_arity=1, label="exp"),
    "log": NodeMapping("math/log", input_arity=1, label="log"),
}

_COMPARISON_NODE_MAP: dict[str, NodeMapping] = {
    "GreaterThan": NodeMapping("cmp/gte", input_arity=2, label=">="),
    "StrictGreaterThan": NodeMapping("cmp/gt", input_arity=2, label=">"),
    "LessThan": NodeMapping("cmp/lte", input_arity=2, label="<="),
    "StrictLessThan": NodeMapping("cmp/lt", input_arity=2, label="<"),
    "Equality": NodeMapping("cmp/eq", input_arity=2, label="=="),
    "Unequality": NodeMapping("cmp/ne", input_arity=2, label="!="),
}

_INDICATOR_NODE_MAP: dict[str, NodeMapping] = {
    "EMA": NodeMapping("indicator/ema", param_names=("period",), input_arity=1, label="ema"),
    "SMA": NodeMapping("indicator/sma", param_names=("period",), input_arity=1, label="sma"),
    "RSI": NodeMapping("indicator/rsi", param_names=("period",), input_arity=1, label="rsi"),
    "MACD": NodeMapping(
        "indicator/macd",
        param_names=("fast", "slow", "signal"),
        input_arity=1,
        label="macd",
    ),
    "VWAP": NodeMapping("indicator/vwap", param_names=(), input_arity=1, label="vwap"),
}


def _sort_key(expr: sp.Expr) -> str:
    try:
        return str(sp.srepr(expr))
    except Exception:  # pragma: no cover - defensive fallback
        return str(expr)


def _normalize_expr(expr: sp.Expr) -> sp.Expr:
    """Apply deterministic simplifications for hashing and mapping.

    Rules (per spec_version):
    - Sort commutative operands for stable ordering.
    - Drop neutral elements (Add 0, Mul 1) when safe.
    - Collapse Pow(x, 1) → x.
    - Normalize numbers to float for consistent downstream params.
    """

    if isinstance(expr, sp.Number):
        return sp.Float(expr)
    if isinstance(expr, sp.Symbol):
        return expr

    args = [_normalize_expr(arg) for arg in expr.args]
    func_name = expr.func.__name__

    args = _maybe_sort_commutative(func_name, args)
    reduced = _maybe_drop_neutral(func_name, args)
    if reduced is not None:
        return reduced

    pow_simplified = _maybe_simplify_pow(func_name, args)
    if pow_simplified is not None:
        return pow_simplified

    try:
        return expr.func(*args, evaluate=False)
    except Exception:  # pragma: no cover - defensive fallback
        return expr


def _maybe_sort_commutative(func_name: str, args: list[sp.Expr]) -> list[sp.Expr]:
    if func_name in _COMMUTATIVE_FUNCS:
        return sorted(args, key=_sort_key)
    return args


def _maybe_drop_neutral(func_name: str, args: list[sp.Expr]) -> sp.Expr | None:
    if func_name not in _NEUTRAL_ELEMENTS:
        return None
    neutral = _NEUTRAL_ELEMENTS[func_name]
    filtered = [arg for arg in args if arg != neutral]
    if not filtered:
        return sp.Float(neutral)
    if len(filtered) == 1:
        return filtered[0]
    return None


def _maybe_simplify_pow(func_name: str, args: list[sp.Expr]) -> sp.Expr | None:
    if func_name == "Pow" and len(args) == 2 and args[1] == 1:
        return args[0]
    return None


def _expression_key(expr: sp.Expr, *, spec_version: str = "v1") -> str:
    """Compute a stable key using normalized Sympy srepr + SHA256."""

    canonical = sp.srepr(_normalize_expr(expr))
    payload = f"{spec_version}:{canonical}"
    return hashlib.sha256(payload.encode()).hexdigest()


class _DagBuilder:
    """Runtime-aware DAG builder from Sympy expressions."""

    def __init__(self) -> None:
        self.nodes: List[dict] = []
        self.edges: List[Tuple[str, str]] = []
        self._id = 0

    def _add(self, node_type: str, *, label: str, inputs: list[str] | None = None, params: dict | None = None) -> str:
        nid = f"n{self._id}"
        payload: dict[str, Any] = {"id": nid, "node_type": node_type, "label": label}
        if params:
            payload["params"] = params
        if inputs:
            payload["inputs"] = inputs
            for src in inputs:
                self.edges.append((src, nid))
        self.nodes.append(payload)
        self._id += 1
        return nid

    def _lookup_mapping(self, func_name: str) -> NodeMapping | None:
        if func_name in _OPERATOR_NODE_MAP:
            return _OPERATOR_NODE_MAP[func_name]
        if func_name in _COMPARISON_NODE_MAP:
            return _COMPARISON_NODE_MAP[func_name]
        indicator = _INDICATOR_NODE_MAP.get(func_name.upper())
        if indicator:
            return indicator
        return None

    def _extract_params(self, mapping: NodeMapping, args: tuple[sp.Expr, ...], func_name: str) -> dict:
        if not mapping.param_names:
            if args:
                raise ValueError(f"Unexpected parameters for {func_name}: {args}")
            return {}

        if len(args) != len(mapping.param_names):
            raise ValueError(
                f"{func_name} expects {len(mapping.param_names)} parameters, got {len(args)}"
            )

        params: dict[str, Any] = {}
        for name, arg in zip(mapping.param_names, args):
            if isinstance(arg, sp.Number):
                params[name] = float(arg)
            else:
                raise ValueError(f"Parameter {name} for {func_name} must be numeric, got {arg!r}")
        return params

    def _maybe_unary_neg(self, node: sp.Expr) -> tuple[bool, sp.Expr]:
        if node.func.__name__ != "Mul" or len(node.args) != 2:
            return False, node
        first, second = node.args
        if isinstance(first, sp.Number) and float(first) == -1:
            return True, second
        return False, node

    def _maybe_division(self, node: sp.Expr) -> tuple[bool, sp.Expr, sp.Expr]:
        if node.func.__name__ != "Mul" or len(node.args) != 2:
            return False, node, node
        left, right = node.args
        if self._is_inverse_pow(right):
            return True, left, right.args[0]
        if self._is_inverse_pow(left):
            return True, right, left.args[0]
        return False, node, node

    def _is_inverse_pow(self, expr: sp.Expr) -> bool:
        if expr.func.__name__ != "Pow" or len(expr.args) != 2:
            return False
        base, exp = expr.args
        return isinstance(exp, sp.Number) and float(exp) == -1.0

    def _maybe_subtraction(self, node: sp.Expr) -> tuple[bool, sp.Expr, sp.Expr]:
        if node.func.__name__ != "Add" or len(node.args) != 2:
            return False, node, node
        left, right = node.args
        neg, target = self._maybe_unary_neg(right)
        if neg:
            return True, left, target
        neg, target = self._maybe_unary_neg(left)
        if neg:
            return True, right, target
        return False, node, node

    def walk(self, node: sp.Expr) -> str:
        if isinstance(node, sp.Symbol):
            return self._add("input", label=f"input:{str(node)}", params={"field": str(node)})
        if isinstance(node, sp.Number):
            return self._add("const", label=f"const:{float(node)}", params={"value": float(node)})
        if node.is_Boolean:  # pragma: no cover - boolean atom
            return self._add("const", label=f"const:{bool(node)}", params={"value": bool(node)})

        func_name = node.func.__name__

        special = self._walk_special(node)
        if special is not None:
            return special

        mapping = self._lookup_mapping(func_name)
        if not mapping:
            raise ValueError(f"Unsupported expression node: {func_name}")

        arity = mapping.input_arity or len(node.args)
        if len(node.args) < arity:
            raise ValueError(f"{func_name} requires {arity} inputs, got {len(node.args)}")

        inputs = [self.walk(arg) for arg in node.args[:arity]]
        params = self._extract_params(mapping, node.args[arity:], func_name)
        label = mapping.label or mapping.node_type
        return self._add(mapping.node_type, label=label, inputs=inputs, params=params)

    def _walk_special(self, node: sp.Expr) -> str | None:
        is_sub, minuend, subtrahend = self._maybe_subtraction(node)
        if is_sub:
            left_id = self.walk(minuend)
            right_id = self.walk(subtrahend)
            return self._add("math/sub", label="sub", inputs=[left_id, right_id])

        is_div, numerator, denominator = self._maybe_division(node)
        if is_div:
            num_id = self.walk(numerator)
            den_id = self.walk(denominator)
            return self._add("math/div", label="div", inputs=[num_id, den_id])

        is_neg, target = self._maybe_unary_neg(node)
        if is_neg:
            target_id = self.walk(target)
            return self._add("math/neg", label="neg", inputs=[target_id])
        return None


def build_expression_dag(
    expr: sp.Expr | str,
    *,
    equation: str,
    complexity: int,
    loss: float,
    data_spec: Mapping[str, Any] | None = None,
    spec_version: str = "v1",
) -> ExpressionDagSpec:
    """Convert a Sympy expression to ExpressionDagSpec."""
    builder = ExpressionDagBuilder(spec_version=spec_version)
    return builder.build(
        expr,
        complexity=complexity,
        loss=loss,
        data_spec=data_spec,
        equation=equation,
    )


class ExpressionDagBuilder:
    """Expression → DAG compiler with normalization and data_spec support."""

    def __init__(self, *, spec_version: str = "v1") -> None:
        self._spec_version = spec_version

    def build(
        self,
        expression: str | sp.Expr,
        *,
        complexity: int | float = 0,
        loss: float = 0.0,
        data_spec: Mapping[str, Any] | None = None,
        equation: str | None = None,
    ) -> ExpressionDagSpec:
        """Build an ExpressionDagSpec from a string or Sympy expression.

        The builder normalizes the expression before computing a stable
        ``expression_key`` so semantically equivalent expressions produce
        identical keys (per spec_version).
        """
        parsed = self._parse(expression)
        normalized = self._normalize(parsed)
        key = self._compute_key(normalized)
        nodes, edges, output = self._compile(normalized)

        return ExpressionDagSpec(
            nodes=nodes,
            edges=edges,
            output=output,
            expression_key=key,
            equation=equation or str(normalized),
            complexity=int(complexity),
            loss=float(loss),
            node_count=len(nodes),
            spec_version=self._spec_version,
            data_spec=dict(data_spec) if isinstance(data_spec, Mapping) else None,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _parse(self, expression: str | sp.Expr) -> sp.Expr:
        if isinstance(expression, sp.Expr):
            return expression
        return sp.sympify(expression)

    def _normalize(self, expr: sp.Expr) -> sp.Expr:
        return _normalize_expr(expr)

    def _compute_key(self, expr: sp.Expr) -> str:
        """Compute versioned expression key."""
        return _expression_key(expr, spec_version=self._spec_version)

    def _compile(self, expr: sp.Expr) -> tuple[List[dict], List[Tuple[str, str]], str]:
        builder = _DagBuilder()
        output = builder.walk(expr)
        return builder.nodes, builder.edges, output
