from __future__ import annotations

from typing import Mapping, TYPE_CHECKING

import polars as pl

from qmtl.runtime.sdk.exceptions import InvalidSchemaError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from polars import DataFrame as PolarsDataFrame

# Built-in DataFrame schemas for node I/O
SCHEMAS: dict[str, dict[str, str]] = {
    "bar": {
        "ts": "Datetime(time_unit='ns', time_zone='UTC')",
        "open": "Float64",
        "high": "Float64",
        "low": "Float64",
        "close": "Float64",
        "volume": "Float64",
    },
    "quote": {
        "ts": "Datetime(time_unit='ns', time_zone='UTC')",
        "bid": "Float64",
        "ask": "Float64",
        "bid_size": "Float64",
        "ask_size": "Float64",
    },
    "trade": {
        "ts": "Datetime(time_unit='ns', time_zone='UTC')",
        "price": "Float64",
        "size": "Float64",
    },
}


def _resolve_schema(expected: str | Mapping[str, str]) -> Mapping[str, str]:
    if isinstance(expected, str):
        try:
            return SCHEMAS[expected]
        except KeyError as e:  # pragma: no cover - defensive
            raise InvalidSchemaError(f"unknown schema: {expected}") from e
    return expected


def validate_schema(df: "PolarsDataFrame", expected: str | Mapping[str, str]) -> None:
    """Validate that ``df`` conforms to ``expected`` schema.

    Parameters
    ----------
    df:
        Input ``polars.DataFrame``.
    expected:
        Built-in schema name (``"bar"``, ``"quote"`` or ``"trade"``) or a
        mapping of column names to ``polars`` dtype strings.

    Raises
    ------
    InvalidSchemaError
        If the dataframe is missing required columns, has unexpected columns or
        column dtypes do not match the schema.
    """

    if not isinstance(df, pl.DataFrame):
        raise InvalidSchemaError("payload must be a polars DataFrame")

    spec = _resolve_schema(expected)

    _ensure_required_columns_present(df, spec)
    _ensure_no_unexpected_columns(df, spec)
    _ensure_column_types_match(df, spec)


def _dtype_to_string(dtype: pl.DataType | None) -> str:
    return str(dtype) if dtype is not None else "Unknown"


def _ensure_required_columns_present(df: "PolarsDataFrame", spec: Mapping[str, str]) -> None:
    missing = [col for col in spec if col not in df.columns]
    if not missing:
        return
    raise InvalidSchemaError(f"missing columns: {', '.join(missing)}")


def _ensure_no_unexpected_columns(df: "PolarsDataFrame", spec: Mapping[str, str]) -> None:
    unexpected = [col for col in df.columns if col not in spec]
    if not unexpected:
        return
    raise InvalidSchemaError(f"unexpected columns: {', '.join(unexpected)}")


def _ensure_column_types_match(df: "PolarsDataFrame", spec: Mapping[str, str]) -> None:
    for col, dtype in spec.items():
        actual = _dtype_to_string(df.schema.get(col))
        if actual != dtype:
            raise InvalidSchemaError(
                f"column '{col}' expected dtype {dtype}, got {actual}"
            )
