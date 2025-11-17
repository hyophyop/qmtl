from __future__ import annotations

from typing import Any, Mapping, TYPE_CHECKING

from qmtl.runtime.sdk.exceptions import InvalidSchemaError

_PANDAS_IMPORT_ERROR: ModuleNotFoundError | None
pandas_module: Any | None
try:  # pragma: no cover - optional dependency shim
    import pandas as _pandas_module  # type: ignore[import-untyped]
    from pandas.api.types import DatetimeTZDtype  # type: ignore[import-untyped]
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when pandas missing
    _PANDAS_IMPORT_ERROR = exc
    pandas_module = None
    DatetimeTZDtype = None
else:  # pragma: no cover - import side effects only
    _PANDAS_IMPORT_ERROR = None
    pandas_module = _pandas_module

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd  # type: ignore[import-untyped]
else:  # pragma: no cover - optional dependency available at runtime
    pd = pandas_module

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


def validate_schema(df: "pd.DataFrame", expected: str | Mapping[str, str]) -> None:
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

    if pd is None or DatetimeTZDtype is None:
        raise ModuleNotFoundError(
            "pandas is required for schema validation; install the 'io' extra"
        ) from _PANDAS_IMPORT_ERROR

    spec = _resolve_schema(expected)

    _ensure_required_columns_present(df, spec)
    _ensure_no_unexpected_columns(df, spec)
    _ensure_column_types_match(df, spec)


def _ensure_required_columns_present(df: "pd.DataFrame", spec: Mapping[str, str]) -> None:
    missing = [col for col in spec if col not in df.columns]
    if not missing:
        return
    raise InvalidSchemaError(f"missing columns: {', '.join(missing)}")


def _ensure_no_unexpected_columns(df: "pd.DataFrame", spec: Mapping[str, str]) -> None:
    unexpected = [col for col in df.columns if col not in spec]
    if not unexpected:
        return
    raise InvalidSchemaError(f"unexpected columns: {', '.join(unexpected)}")


def _ensure_column_types_match(df: "pd.DataFrame", spec: Mapping[str, str]) -> None:
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
