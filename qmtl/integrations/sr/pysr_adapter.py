"""Utilities to convert PySR hall_of_fame.csv into DAG specs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

import sympy as sp

from .dag import ExpressionDagSpec, build_expression_dag

REQUIRED_COLS = {"Equation", "Complexity", "Loss"}


def _latest_hof(base: Path) -> Path:
    candidates = sorted(base.glob("*/hall_of_fame.csv"))
    if not candidates:
        raise FileNotFoundError(f"No hall_of_fame.csv found under {base}")
    return candidates[-1]


def _load_rows(hof_path: Path) -> List[dict]:
    with hof_path.open() as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        if not REQUIRED_COLS.issubset(cols):
            raise ValueError(f"HOF missing columns {REQUIRED_COLS}, found {cols}")
        return list(reader)


def load_pysr_hof_as_dags(
    hof_path: Path | None = None,
    *,
    outputs_base: Path | None = None,
    max_nodes: int = 20,
    data_spec: dict | None = None,
    spec_version: str = "v1",
) -> List[ExpressionDagSpec]:
    """Load PySR hall_of_fame.csv and return filtered DAG specs.

    Args:
        hof_path: explicit path to hall_of_fame.csv. If None, pick the latest under outputs_base.
        outputs_base: base directory to search for HOF when hof_path is None (default: outputs/).
        max_nodes: drop expressions whose DAG node_count exceeds this threshold.
        data_spec: optional data snapshot specification to embed for consistency checks.
        spec_version: expression spec version to use for hashing/normalization.
    """
    if hof_path is None:
        base = outputs_base or Path("outputs")
        hof_path = _latest_hof(base)

    rows = _load_rows(hof_path)

    specs: List[ExpressionDagSpec] = []
    for row in rows:
        eq = str(row["Equation"])
        complexity = int(row["Complexity"])
        loss = float(row["Loss"])
        try:
            expr = sp.sympify(eq)
            spec = build_expression_dag(
                expr,
                equation=eq,
                complexity=complexity,
                loss=loss,
                data_spec=data_spec,
                spec_version=spec_version,
            )
        except Exception as exc:  # pragma: no cover - defensive
            # Skip unparseable rows.
            print(f"[skip] failed to parse '{eq}': {exc}")
            continue

        if spec.node_count > max_nodes:
            print(f"[skip] node_count {spec.node_count} > {max_nodes}: {eq}")
            continue

        specs.append(spec)

    return specs
