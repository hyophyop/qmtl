"""Minimal Expression DAG spec and Sympy converter."""

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


class _DagBuilder:
    """Simple DAG builder from Sympy expressions."""

    def __init__(self) -> None:
        self.nodes: List[dict] = []
        self.edges: List[Tuple[str, str]] = []
        self._id = 0

    def _add(self, label: str) -> str:
        nid = f"n{self._id}"
        self.nodes.append({"id": nid, "label": label})
        self._id += 1
        return nid

    def walk(self, node: sp.Expr) -> str:
        if isinstance(node, sp.Symbol):
            return self._add(f"var:{str(node)}")
        if isinstance(node, sp.Number):
            return self._add(f"const:{float(node)}")

        head = type(node).__name__
        nid = self._add(f"op:{head}")
        for arg in node.args:
            cid = self.walk(arg)
            self.edges.append((cid, nid))
        return nid


def _expression_key(expr: sp.Expr, *, spec_version: str = "v1") -> str:
    """Compute a stable key using Sympy srepr + SHA256."""
    canonical = sp.srepr(expr)
    payload = f"{spec_version}:{canonical}"
    return hashlib.sha256(payload.encode()).hexdigest()


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
    builder = _DagBuilder()
    parsed = sp.sympify(expr)
    output = builder.walk(parsed)
    key = _expression_key(parsed, spec_version=spec_version)
    return ExpressionDagSpec(
        nodes=builder.nodes,
        edges=builder.edges,
        output=output,
        expression_key=key,
        equation=equation,
        complexity=int(complexity),
        loss=float(loss),
        node_count=len(builder.nodes),
        spec_version=spec_version,
        data_spec=dict(data_spec) if isinstance(data_spec, Mapping) else None,
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
            equation=str(parsed),
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
        """Best-effort normalization: simplify while keeping structure stable."""
        try:
            return sp.simplify(expr)
        except Exception:  # pragma: no cover - defensive
            return expr

    def _compute_key(self, expr: sp.Expr) -> str:
        """Compute versioned expression key."""
        return _expression_key(expr, spec_version=self._spec_version)

    def _compile(self, expr: sp.Expr) -> tuple[List[dict], List[Tuple[str, str]], str]:
        builder = _DagBuilder()
        output = builder.walk(expr)
        return builder.nodes, builder.edges, output
