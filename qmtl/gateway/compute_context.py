from __future__ import annotations

"""Gateway-facing helpers for compute context handling.

This module now re-exports the canonical compute context utilities housed in
``qmtl.common.compute_context`` to preserve import stability for gateway
consumers.
"""

from qmtl.common.compute_context import (
    ComputeContext,
    build_strategy_compute_context,
    evaluate_safe_mode,
    normalize_context_value,
    resolve_execution_domain,
)

__all__ = [
    "ComputeContext",
    "build_strategy_compute_context",
    "evaluate_safe_mode",
    "normalize_context_value",
    "resolve_execution_domain",
]
