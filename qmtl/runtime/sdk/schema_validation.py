from __future__ import annotations

from typing import Dict

import polars as pl

from .exceptions import NodeValidationError

__all__ = ["validate_schema"]

def validate_schema(df: pl.DataFrame, expected_schema: Dict[str, str]) -> None:
    """Validate ``df`` against ``expected_schema``.

    ``expected_schema`` maps column names to polars dtype strings. Raises
    :class:`NodeValidationError` if columns are missing or dtypes mismatch.
    """
    if not isinstance(df, pl.DataFrame):
        raise NodeValidationError("payload must be a polars DataFrame")

    missing = [col for col in expected_schema if col not in df.columns]
    if missing:
        raise NodeValidationError(f"missing columns: {missing}")

    mismatched: Dict[str, tuple[str, str]] = {}
    for col, dtype in expected_schema.items():
        if col in df.columns:
            actual = df.schema.get(col)
            actual_str = str(actual) if actual is not None else "Unknown"
            if actual_str != dtype:
                mismatched[col] = (dtype, actual_str)
    if mismatched:
        details = ", ".join(
            f"{col} (expected {exp}, got {got})" for col, (exp, got) in mismatched.items()
        )
        raise NodeValidationError(f"dtype mismatch: {details}")
