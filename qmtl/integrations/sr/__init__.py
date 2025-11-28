"""Strategy Recommendation (SR) integration utilities.

This module provides tools for integrating SR (Strategy Recommendation) engines
like PySR and Operon with QMTL's strategy submission and validation pipeline.

Key Components
--------------
Types:
    - SRCandidate: Protocol for SR engine candidates
    - BaseSRCandidate: Base implementation of SRCandidate
    - PySRCandidate: PySR-specific candidate
    - OperonCandidate: Operon-specific candidate

DAG:
    - ExpressionDagSpec: DAG specification for Sympy expressions
    - build_expression_dag: Convert Sympy expression to DAG spec
    - ExpressionDagBuilder: Normalized DAG builder with data_spec support

Adapters:
    - load_pysr_hof_as_dags: Load PySR hall_of_fame.csv as DAG specs
    - load_pysr_hof_as_strategies: Load PySR hall_of_fame.csv as Strategy classes
    - adapters: Subpackage with generic and Operon adapters

Strategy Templates:
    - build_expression_strategy: Build a Strategy from expression + data_spec
    - build_strategy_from_dag_spec: Build a Strategy from ExpressionDagSpec-like objects

Expression Keys:
    - compute_expression_key: Generate stable keys for deduplication
    - normalize_ast: Normalize expression AST for canonical form

Submitters:
    - (제거됨) Phase 1 리셋 이후 제출기는 제공하지 않음

Example
-------
>>> from qmtl.integrations.sr import (
...     load_pysr_hof_as_dags,
...     BaseSRCandidate,
...     compute_expression_key,
... )
>>> # Load PySR results
>>> dags = load_pysr_hof_as_dags(max_nodes=20)
>>> # Generate expression key for deduplication
>>> key = compute_expression_key("x + y")
"""

# Types
from .types import (  # noqa: F401
    SRCandidate,
    BaseSRCandidate,
    PySRCandidate,
    OperonCandidate,
)

# DAG
from .dag import (  # noqa: F401
    ExpressionDagSpec,
    build_expression_dag,
    ExpressionDagBuilder,
)

# Adapters
from .pysr_adapter import load_pysr_hof_as_dags, load_pysr_hof_as_strategies  # noqa: F401
from . import adapters  # noqa: F401

# Strategy Templates
from .strategy_template import (  # noqa: F401
    build_expression_strategy,
    build_strategy_from_dag_spec,
    submit_with_validation,
    validate_strategy_against_sample,
    ValidationSample,
    ValidationSampleMismatch,
    ValidationResult,
)

# Expression Keys
from .expression_key import (  # noqa: F401
    compute_expression_key,
    normalize_ast,
)

__all__ = [
    # Types
    "SRCandidate",
    "BaseSRCandidate",
    "PySRCandidate",
    "OperonCandidate",
    # DAG
    "ExpressionDagSpec",
    "build_expression_dag",
    "ExpressionDagBuilder",
    # Adapters
    "load_pysr_hof_as_dags",
    "load_pysr_hof_as_strategies",
    "adapters",
    # Strategy Templates
    "build_expression_strategy",
    "build_strategy_from_dag_spec",
    "submit_with_validation",
    "validate_strategy_against_sample",
    "ValidationSample",
    "ValidationSampleMismatch",
    "ValidationResult",
    # Expression Keys
    "compute_expression_key",
    "normalize_ast",
]
