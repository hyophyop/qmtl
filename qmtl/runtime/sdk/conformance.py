from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from .schema_validation import validate_schema


@dataclass(frozen=True)
class ConformanceReport:
    """Summary of the normalization steps applied to a payload."""

    warnings: tuple[str, ...] = ()
    flags_counts: dict[str, int] = field(default_factory=dict)


class ConformancePipeline:
    """Normalize Seamless provider frames and surface data quality findings."""

    _TS_COLUMN = "ts"

    def normalize(
        self,
        df: pd.DataFrame,
        *,
        schema: dict | None = None,
        interval: int | None = None,
    ) -> tuple[pd.DataFrame, ConformanceReport]:
        """Return a normalized copy of ``df`` and a report of applied fixes.

        Parameters
        ----------
        df:
            Payload to normalize. A defensive copy is created to avoid mutating
            caller owned frames.
        schema:
            Optional schema declaration. Supports the following shapes:

            * ``{"col": "dtype"}``
            * ``{"fields": [{"name": "col", "dtype": "float64"}]}``

            Only the declared dtypes are enforced. Missing columns are
            reported as warnings.
        interval:
            Expected spacing (in the same units as ``ts``) between consecutive
            rows. When provided, gaps and duplicates are tracked.
        """

        if not isinstance(df, pd.DataFrame):  # pragma: no cover - defensive
            raise TypeError("ConformancePipeline only supports pandas DataFrames")

        working = df.copy(deep=True)
        warnings: list[str] = []
        flags: dict[str, int] = {}

        expected_schema = self._extract_schema_mapping(schema)
        if expected_schema:
            self._enforce_schema(working, expected_schema, flags, warnings)

        if self._TS_COLUMN in working.columns:
            self._normalize_timestamps(working, interval, flags, warnings)
        else:
            warnings.append("missing ts column; skipping temporal normalization")

        return working, ConformanceReport(warnings=tuple(warnings), flags_counts=flags)

    # ------------------------------------------------------------------
    # schema handling helpers
    # ------------------------------------------------------------------
    def _extract_schema_mapping(self, schema: dict | None) -> dict[str, str]:
        if schema is None:
            return {}
        if isinstance(schema, dict):
            if "fields" in schema and isinstance(schema["fields"], Iterable):
                mapping: dict[str, str] = {}
                for field in schema["fields"]:  # type: ignore[assignment]
                    if not isinstance(field, dict):
                        continue
                    name = field.get("name")
                    dtype = field.get("dtype") or field.get("type")
                    if isinstance(name, str) and isinstance(dtype, str):
                        mapping[name] = dtype
                return mapping
            if all(isinstance(k, str) and isinstance(v, str) for k, v in schema.items()):
                return {k: v for k, v in schema.items() if k != "schema_compat_id"}
        return {}

    def _enforce_schema(
        self,
        df: pd.DataFrame,
        expected_schema: dict[str, str],
        flags: dict[str, int],
        warnings: list[str],
    ) -> None:
        try:
            validate_schema(df, expected_schema)
        except Exception as exc:  # pragma: no cover - validation already tested
            warnings.append(str(exc))
            # Attempt best-effort casts for known columns so downstream logic
            # can still operate on normalized dtypes.
        casts = 0
        for column, dtype in expected_schema.items():
            if column not in df.columns:
                continue
            current = str(df[column].dtype)
            if current == dtype:
                continue
            try:
                df[column] = df[column].astype(dtype)
                casts += 1
            except Exception:  # pragma: no cover - dtype conversion failures
                warnings.append(
                    f"failed to cast column '{column}' to {dtype}; observed {current}"
                )
        if casts:
            flags["dtype_casts"] = casts

    # ------------------------------------------------------------------
    # temporal normalization helpers
    # ------------------------------------------------------------------
    def _normalize_timestamps(
        self,
        df: pd.DataFrame,
        interval: int | None,
        flags: dict[str, int],
        warnings: list[str],
    ) -> None:
        ts = df[self._TS_COLUMN]
        if not pd.api.types.is_integer_dtype(ts.dtype):
            try:
                df[self._TS_COLUMN] = pd.to_datetime(ts).astype("int64") // 10**6
                flags["ts_casts"] = flags.get("ts_casts", 0) + len(df)
            except Exception:  # pragma: no cover - cast failures are unexpected
                warnings.append("failed to convert ts column to int64 timestamps")
                return

        df.sort_values(self._TS_COLUMN, inplace=True)
        df.reset_index(drop=True, inplace=True)

        if interval is not None and interval > 0:
            arr = df[self._TS_COLUMN].to_numpy()
            if arr.size:
                deltas = np.diff(arr)
                duplicates = int(np.sum(deltas == 0))
                if duplicates:
                    flags["duplicate_bars"] = duplicates
                    warnings.append(f"dropped {duplicates} duplicate bars")
                    df.drop_duplicates(subset=[self._TS_COLUMN], keep="last", inplace=True)
                    df.reset_index(drop=True, inplace=True)
                    arr = df[self._TS_COLUMN].to_numpy()
                    deltas = np.diff(arr)

                missing = int(np.sum(np.maximum(deltas // interval - 1, 0)))
                if missing:
                    flags["missing_bars"] = missing
                    warnings.append(
                        f"detected {missing} interval gaps for interval={interval}"
                    )
        else:
            # Still drop duplicate bars even without interval metadata.
            duplicates = int(df.duplicated(subset=[self._TS_COLUMN], keep="last").sum())
            if duplicates:
                flags["duplicate_bars"] = duplicates
                warnings.append(f"dropped {duplicates} duplicate bars (interval unknown)")
                df.drop_duplicates(subset=[self._TS_COLUMN], keep="last", inplace=True)
                df.reset_index(drop=True, inplace=True)


__all__ = ["ConformancePipeline", "ConformanceReport"]

