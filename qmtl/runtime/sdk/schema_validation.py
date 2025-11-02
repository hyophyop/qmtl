from __future__ import annotations

from typing import Dict

import pandas as pd

from .exceptions import NodeValidationError

__all__ = ["validate_schema"]

def validate_schema(df: pd.DataFrame, expected_schema: Dict[str, str]) -> None:
    """Validate ``df`` against ``expected_schema``.

    ``expected_schema`` maps column names to pandas dtype strings. Raises
    :class:`NodeValidationError` if columns are missing or dtypes mismatch.
    """
    if not isinstance(df, pd.DataFrame):
        raise NodeValidationError("payload must be a pandas DataFrame")

    missing = [col for col in expected_schema if col not in df.columns]
    if missing:
        raise NodeValidationError(f"missing columns: {missing}")

    mismatched: Dict[str, tuple[str, str]] = {}
    for col, dtype in expected_schema.items():
        if col in df.columns and str(df[col].dtype) != dtype:
            mismatched[col] = (dtype, str(df[col].dtype))
    if mismatched:
        details = ", ".join(
            f"{col} (expected {exp}, got {got})" for col, (exp, got) in mismatched.items()
        )
        raise NodeValidationError(f"dtype mismatch: {details}")
