from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from .exceptions import NodeValidationError
from .schema_validation import validate_schema


@dataclass(frozen=True)
class ConformanceReport:
    """Summary of the normalization steps applied to a payload."""

    warnings: tuple[str, ...] = ()
    flags_counts: dict[str, int] = field(default_factory=dict)


class ConformancePipeline:
    """Normalize Seamless provider frames and surface data quality findings."""

    _TS_COLUMN = "ts"
    _NS_PER_SECOND = 10**9

    _FLAG_DUPLICATE_TS = "duplicate_ts"
    _FLAG_GAP = "gap"
    _FLAG_MISSING_COLUMN = "missing_column"
    _FLAG_DTYPE_CAST = "dtype_cast"
    _FLAG_DTYPE_MISMATCH = "dtype_mismatch"
    _FLAG_TS_CAST = "ts_cast"
    _FLAG_TS_TIMEZONE = "ts_timezone_normalized"
    _FLAG_NON_FINITE = "non_finite"
    _FLAG_INVALID_TS = "invalid_timestamp"

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

        self._normalize_non_finite_values(working, flags, warnings)

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
        missing_columns = [col for col in expected_schema if col not in df.columns]
        if missing_columns:
            flags[self._FLAG_MISSING_COLUMN] = (
                flags.get(self._FLAG_MISSING_COLUMN, 0) + len(missing_columns)
            )
            warnings.append(
                "missing columns detected: " + ", ".join(sorted(missing_columns))
            )

        try:
            validate_schema(df, expected_schema)
        except NodeValidationError as exc:
            warnings.append(str(exc))
        except Exception as exc:  # pragma: no cover - defensive guard
            warnings.append(str(exc))

        for column, dtype in expected_schema.items():
            if column not in df.columns:
                continue
            current_dtype = str(df[column].dtype)
            if current_dtype == dtype:
                continue
            try:
                df[column] = df[column].astype(dtype)
                flags[self._FLAG_DTYPE_CAST] = (
                    flags.get(self._FLAG_DTYPE_CAST, 0) + 1
                )
                warnings.append(
                    f"cast column '{column}' from {current_dtype} to {dtype}"
                )
            except Exception:
                flags[self._FLAG_DTYPE_MISMATCH] = (
                    flags.get(self._FLAG_DTYPE_MISMATCH, 0) + 1
                )
                warnings.append(
                    f"failed to normalize column '{column}' to {dtype}; observed {current_dtype}"
                )

    def _normalize_non_finite_values(
        self,
        df: pd.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> None:
        replacements = 0
        observed_nan = 0
        for column in df.columns:
            series = df[column]
            if not pd.api.types.is_numeric_dtype(series):
                continue
            if series.empty:
                continue
            nan_count = int(pd.isna(series).sum())
            values = series.to_numpy(copy=False)
            mask_inf = np.isinf(values)
            inf_count = int(mask_inf.sum())
            if inf_count:
                series = series.astype("float64")
                series.iloc[np.where(mask_inf)[0]] = np.nan
                df[column] = series
                replacements += inf_count
            observed_nan += nan_count
        total = replacements + observed_nan
        if replacements:
            warnings.append(
                f"replaced {replacements} +/-inf values with NaN for numeric columns"
            )
        if total:
            flags[self._FLAG_NON_FINITE] = flags.get(self._FLAG_NON_FINITE, 0) + total

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
        dtype = ts.dtype

        cast_rows, timezone_adjusted = self._cast_timestamp_column(df, dtype, flags, warnings)

        if cast_rows:
            flags[self._FLAG_TS_CAST] = flags.get(self._FLAG_TS_CAST, 0) + cast_rows
        if timezone_adjusted:
            flags[self._FLAG_TS_TIMEZONE] = (
                flags.get(self._FLAG_TS_TIMEZONE, 0) + timezone_adjusted
            )

        if df.empty:
            return

        self._sort_and_dedupe_timestamps(df, flags, warnings)
        if df.empty:
            return

        if interval is None or interval <= 0 or len(df) < 2:
            return

        arr = df[self._TS_COLUMN].to_numpy(copy=False)
        gap_bars, misaligned = self._detect_interval_gaps(arr, interval)

        if gap_bars:
            flags[self._FLAG_GAP] = flags.get(self._FLAG_GAP, 0) + gap_bars
            warnings.append(
                f"detected {gap_bars} missing bars for interval={interval}"
            )
        if misaligned:
            warnings.append(
                f"detected {misaligned} gaps with misaligned boundaries for interval={interval}"
            )

    def _cast_timestamp_column(
        self,
        df: pd.DataFrame,
        dtype: object,
        flags: dict[str, int],
        warnings: list[str],
    ) -> tuple[int, int]:
        ts = df[self._TS_COLUMN]
        if isinstance(dtype, pd.DatetimeTZDtype):
            converted = ts.dt.tz_convert("UTC")
            df[self._TS_COLUMN] = self._timestamps_to_seconds(converted)
            return len(df), len(df)
        if pd.api.types.is_datetime64_dtype(dtype):
            df[self._TS_COLUMN] = self._timestamps_to_seconds(ts)
            return len(df), 0
        if pd.api.types.is_integer_dtype(dtype):
            cast_rows = self._normalize_integer_epoch(df, flags, warnings)
            return cast_rows, 0
        return self._cast_flexible_timestamps(df, dtype, flags, warnings)

    def _cast_flexible_timestamps(
        self,
        df: pd.DataFrame,
        dtype: object,
        flags: dict[str, int],
        warnings: list[str],
    ) -> tuple[int, int]:
        ts = df[self._TS_COLUMN]
        converted = pd.to_datetime(ts, utc=True, errors="coerce")
        invalid_mask = converted.isna()
        if invalid_mask.any():
            invalid_count = int(invalid_mask.sum())
            warnings.append(f"dropped {invalid_count} rows with invalid timestamps")
            flags[self._FLAG_INVALID_TS] = (
                flags.get(self._FLAG_INVALID_TS, 0) + invalid_count
            )
            df.drop(index=df.index[invalid_mask], inplace=True)
            df.reset_index(drop=True, inplace=True)
            if df.empty:
                return 0, 0
            converted = converted[~invalid_mask].reset_index(drop=True)

        df[self._TS_COLUMN] = self._timestamps_to_seconds(converted)
        timezone_adjusted = 0
        if isinstance(dtype, pd.DatetimeTZDtype) or getattr(dtype, "tz", None) is not None:
            timezone_adjusted = len(df)
        return len(df), timezone_adjusted

    def _sort_and_dedupe_timestamps(
        self,
        df: pd.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> None:
        df.sort_values(self._TS_COLUMN, inplace=True)
        df.reset_index(drop=True, inplace=True)

        duplicates_mask = df.duplicated(subset=[self._TS_COLUMN], keep="last")
        duplicates = int(duplicates_mask.sum())
        if not duplicates:
            return
        df.drop(index=df.index[duplicates_mask], inplace=True)
        df.reset_index(drop=True, inplace=True)
        flags[self._FLAG_DUPLICATE_TS] = (
            flags.get(self._FLAG_DUPLICATE_TS, 0) + duplicates
        )
        warnings.append(f"dropped {duplicates} duplicate bars")

    def _detect_interval_gaps(self, arr: np.ndarray, interval: int) -> tuple[int, int]:
        if arr.size < 2:
            return 0, 0
        deltas = np.diff(arr)
        gap_bars = 0
        misaligned = 0
        for delta in deltas:
            if delta <= 0:
                continue
            if delta > interval:
                gap_bars += int((delta - interval) // interval)
                if (delta - interval) % interval:
                    misaligned += 1
        return gap_bars, misaligned

    def _timestamps_to_seconds(self, series: pd.Series) -> pd.Series:
        as_int = series.astype("int64", copy=False)
        return (as_int // self._NS_PER_SECOND).astype("int64", copy=False)

    def _normalize_integer_epoch(
        self,
        df: pd.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> int:
        ts = df[self._TS_COLUMN]
        invalid_mask = pd.isna(ts)
        if invalid_mask.any():
            invalid_count = int(invalid_mask.sum())
            warnings.append(f"dropped {invalid_count} rows with invalid timestamps")
            flags[self._FLAG_INVALID_TS] = (
                flags.get(self._FLAG_INVALID_TS, 0) + invalid_count
            )
            df.drop(index=df.index[invalid_mask], inplace=True)
            df.reset_index(drop=True, inplace=True)
            if df.empty:
                return 0
            ts = df[self._TS_COLUMN]

        normalized = ts.astype("int64", copy=False)
        divisor = self._infer_epoch_divisor(normalized)
        cast_rows = 0
        if divisor != 1:
            normalized = normalized // divisor
            cast_rows = len(df)
        df[self._TS_COLUMN] = normalized
        return cast_rows

    def _infer_epoch_divisor(self, series: pd.Series) -> int:
        if series.empty:
            return 1
        values = np.abs(series.to_numpy(copy=False))
        if not len(values):
            return 1
        non_zero = values[values > 0]
        if not len(non_zero):
            return 1

        max_value = int(non_zero.max())
        # Treat small magnitudes as already being in the desired resolution (seconds).
        # This prevents arbitrary integers such as [1_000, 4_000, ...] from being
        # interpreted as millisecond epochs and down-casted unexpectedly.
        if max_value < 10**10:
            return 1

        unique_sorted = np.unique(non_zero)
        if unique_sorted.size >= 2:
            diffs = np.diff(unique_sorted)
            positive_diffs = diffs[diffs > 0]
            if positive_diffs.size:
                min_diff = int(positive_diffs.min())
                for divisor in (10**9, 10**6, 10**3):
                    if min_diff % divisor == 0:
                        return divisor

        if max_value >= 10**16:
            return 10**9
        if max_value >= 10**13:
            return 10**6
        if max_value >= 10**10:
            return 10**3
        return 1


__all__ = ["ConformancePipeline", "ConformanceReport"]
