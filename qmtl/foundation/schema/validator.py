from __future__ import annotations

from typing import Mapping

import pandas as pd
from pandas.api.types import DatetimeTZDtype

from qmtl.runtime.sdk.exceptions import InvalidSchemaError

# Built-in DataFrame schemas for node I/O
SCHEMAS: dict[str, dict[str, str]] = {
    "bar": {
        "ts": "datetime64[ns, UTC]",
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "float64",
    },
    "quote": {
        "ts": "datetime64[ns, UTC]",
        "bid": "float64",
        "ask": "float64",
        "bid_size": "float64",
        "ask_size": "float64",
    },
    "trade": {
        "ts": "datetime64[ns, UTC]",
        "price": "float64",
        "size": "float64",
    },
}


def _resolve_schema(expected: str | Mapping[str, str]) -> Mapping[str, str]:
    if isinstance(expected, str):
        try:
            return SCHEMAS[expected]
        except KeyError as e:  # pragma: no cover - defensive
            raise InvalidSchemaError(f"unknown schema: {expected}") from e
    return expected


def validate_schema(df: pd.DataFrame, expected: str | Mapping[str, str]) -> None:
    """Validate that ``df`` conforms to ``expected`` schema.

    Parameters
    ----------
    df:
        Input ``pandas.DataFrame``.
    expected:
        Built-in schema name (``"bar"``, ``"quote"`` or ``"trade"``) or a
        mapping of column names to ``pandas`` dtypes.

    Raises
    ------
    InvalidSchemaError
        If the dataframe is missing required columns, has unexpected columns or
        column dtypes do not match the schema.
    """

    spec = _resolve_schema(expected)

    missing = [col for col in spec if col not in df.columns]
    if missing:
        raise InvalidSchemaError(f"missing columns: {', '.join(missing)}")

    unexpected = [col for col in df.columns if col not in spec]
    if unexpected:
        raise InvalidSchemaError(f"unexpected columns: {', '.join(unexpected)}")

    for col, dtype in spec.items():
        series = df[col]
        if col == "ts":
            if not isinstance(series.dtype, DatetimeTZDtype):
                raise InvalidSchemaError("ts column must be timezone-aware")
            if str(series.dtype.tz) != "UTC":
                raise InvalidSchemaError("ts column must be in UTC")
            continue
        if str(series.dtype) != dtype:
            raise InvalidSchemaError(
                f"column '{col}' expected dtype {dtype}, got {series.dtype}"
            )

