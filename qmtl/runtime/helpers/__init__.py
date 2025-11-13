"""Shared runtime helper utilities.

This package centralizes helper routines that are shared across the
runtime-facing modules.  Keeping the helpers colocated makes it easier to
control their complexity and to add focused unit coverage.
"""

from .runtime import (  # noqa: F401
    ActivationMetadata,
    ActivationUpdate,
    ExecutionContextResolution,
    adjust_returns_for_costs,
    apply_temporal_requirements,
    calculate_execution_metrics,
    compute_alpha_performance_summary,
    determine_execution_mode,
    normalize_clock_value,
    normalize_weight,
    parse_activation_update,
)

__all__ = [
    "ActivationMetadata",
    "ActivationUpdate",
    "ExecutionContextResolution",
    "adjust_returns_for_costs",
    "apply_temporal_requirements",
    "calculate_execution_metrics",
    "compute_alpha_performance_summary",
    "determine_execution_mode",
    "normalize_clock_value",
    "normalize_weight",
    "parse_activation_update",
]
