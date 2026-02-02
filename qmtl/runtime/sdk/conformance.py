from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Any, cast

import numpy as np
import polars as pl
from typing import Literal, cast
from numpy.typing import NDArray

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
        df: pl.DataFrame,
        *,
        schema: dict | None = None,
        interval: int | None = None,
    ) -> tuple[pl.DataFrame, ConformanceReport]:
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

        if not isinstance(df, pl.DataFrame):  # pragma: no cover - defensive
            raise TypeError("ConformancePipeline only supports polars DataFrames")

        working = df.clone()
        warnings: list[str] = []
        flags: dict[str, int] = {}

        expected_schema = self._extract_schema_mapping(schema)
        if expected_schema:
            working = self._enforce_schema(working, expected_schema, flags, warnings)

        working = self._normalize_non_finite_values(working, flags, warnings)

        if self._TS_COLUMN in working.columns:
            working = self._normalize_timestamps(working, interval, flags, warnings)
        else:
            warnings.append("missing ts column; skipping temporal normalization")

        return working, ConformanceReport(warnings=tuple(warnings), flags_counts=flags)

    # ------------------------------------------------------------------
    # schema handling helpers
    # ------------------------------------------------------------------
    def _extract_schema_mapping(self, schema: dict | None) -> dict[str, str]:
        if not isinstance(schema, dict):
            return {}
        if "fields" in schema:
            mapping = self._normalize_field_schema(schema.get("fields"))
            if mapping:
                return mapping
        return self._normalize_flat_schema(schema)

    def _normalize_field_schema(self, fields: Iterable[Any] | None) -> dict[str, str]:
        if not isinstance(fields, Iterable) or isinstance(fields, (str, bytes)):
            return {}
        mapping: dict[str, str] = {}
        for entry in fields:
            name, dtype = self._extract_field_entry(entry)
            if name is not None and dtype is not None:
                mapping[name] = dtype
        return mapping

    def _extract_field_entry(self, entry: Any) -> tuple[str | None, str | None]:
        if not isinstance(entry, dict):
            return None, None
        name = entry.get("name")
        dtype = entry.get("dtype") or entry.get("type")
        if isinstance(name, str) and isinstance(dtype, str):
            return name, dtype
        return None, None

    def _normalize_flat_schema(self, schema: dict[Any, Any]) -> dict[str, str]:
        return {
            key: value
            for key, value in schema.items()
            if key != "schema_compat_id"
            and isinstance(key, str)
            and isinstance(value, str)
        }

    def _enforce_schema(
        self,
        df: pl.DataFrame,
        expected_schema: dict[str, str],
        flags: dict[str, int],
        warnings: list[str],
    ) -> pl.DataFrame:
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
            current_dtype = str(df.schema.get(column))
            if current_dtype == dtype:
                continue
            try:
                target_dtype = _parse_polars_dtype(dtype)
                if target_dtype is None:
                    raise ValueError(f"unknown polars dtype: {dtype}")
                df = df.with_columns(pl.col(column).cast(target_dtype, strict=False))
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
        return df

    def _normalize_non_finite_values(
        self,
        df: pl.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> pl.DataFrame:
        replacements = 0
        observed_nan = 0
        for column, dtype in df.schema.items():
            if not _is_numeric_dtype(dtype):
                continue
            series = df.get_column(column)
            if len(series) == 0:
                continue
            is_float = _is_float_dtype(dtype)
            nan_count = int(series.is_nan().sum()) if is_float else 0
            null_count = int(series.is_null().sum())
            inf_count = int(series.is_infinite().sum()) if is_float else 0
            if inf_count:
                df = df.with_columns(
                    pl.when(pl.col(column).is_infinite())
                    .then(None)
                    .otherwise(pl.col(column))
                    .alias(column)
                )
                replacements += inf_count
            observed_nan += nan_count + null_count
        total = replacements + observed_nan
        if replacements:
            warnings.append(
                f"replaced {replacements} +/-inf values with NaN for numeric columns"
            )
        if total:
            flags[self._FLAG_NON_FINITE] = flags.get(self._FLAG_NON_FINITE, 0) + total
        return df

    # ------------------------------------------------------------------
    # temporal normalization helpers
    # ------------------------------------------------------------------
    def _normalize_timestamps(
        self,
        df: pl.DataFrame,
        interval: int | None,
        flags: dict[str, int],
        warnings: list[str],
    ) -> pl.DataFrame:
        dtype = df.schema.get(self._TS_COLUMN)

        df, cast_rows, timezone_adjusted = self._cast_timestamp_column(df, dtype, flags, warnings)

        if cast_rows:
            flags[self._FLAG_TS_CAST] = flags.get(self._FLAG_TS_CAST, 0) + cast_rows
        if timezone_adjusted:
            flags[self._FLAG_TS_TIMEZONE] = (
                flags.get(self._FLAG_TS_TIMEZONE, 0) + timezone_adjusted
            )

        if df.is_empty():
            return df

        df = self._sort_and_dedupe_timestamps(df, flags, warnings)

        if interval is None or interval <= 0 or df.height < 2:
            return df

        arr = df.get_column(self._TS_COLUMN).to_numpy()
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
        return df

    def _cast_timestamp_column(
        self,
        df: pl.DataFrame,
        dtype: pl.DataType | None,
        flags: dict[str, int],
        warnings: list[str],
    ) -> tuple[pl.DataFrame, int, int]:
        if dtype is None:
            return self._cast_flexible_timestamps(df, flags, warnings)

        if _is_datetime_dtype(dtype):
            timezone_adjusted = 0
            if getattr(dtype, "time_zone", None):
                df = df.with_columns(
                    pl.col(self._TS_COLUMN)
                    .dt.convert_time_zone("UTC")
                    .alias(self._TS_COLUMN)
                )
                timezone_adjusted = df.height
            df = df.with_columns(
                self._timestamps_to_seconds(pl.col(self._TS_COLUMN)).alias(self._TS_COLUMN)
            )
            return df, df.height, timezone_adjusted

        if _is_integer_dtype(dtype):
            cast_rows, df = self._normalize_integer_epoch(df, flags, warnings)
            return df, cast_rows, 0

        if _is_numeric_dtype(dtype):
            df = df.with_columns(pl.col(self._TS_COLUMN).cast(pl.Int64, strict=False))
            cast_rows, df = self._normalize_integer_epoch(df, flags, warnings)
            return df, cast_rows, 0

        return self._cast_flexible_timestamps(df, flags, warnings)

    def _cast_flexible_timestamps(
        self,
        df: pl.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> tuple[pl.DataFrame, int, int]:
        converted = df.select(
            pl.col(self._TS_COLUMN)
            .cast(pl.Datetime(time_unit="ns", time_zone="UTC"), strict=False)
            .alias(self._TS_COLUMN)
        )
        invalid_mask = converted.get_column(self._TS_COLUMN).is_null()
        invalid_count = int(invalid_mask.sum())
        if invalid_count:
            warnings.append(f"dropped {invalid_count} rows with invalid timestamps")
            flags[self._FLAG_INVALID_TS] = (
                flags.get(self._FLAG_INVALID_TS, 0) + invalid_count
            )
            df = df.filter(~pl.col(self._TS_COLUMN).cast(pl.Datetime(time_unit="ns", time_zone="UTC"), strict=False).is_null())
            if df.is_empty():
                return df, 0, 0

        df = df.with_columns(
            pl.col(self._TS_COLUMN)
            .cast(pl.Datetime(time_unit="ns", time_zone="UTC"), strict=False)
            .dt.timestamp("ms")
            .floordiv(1000)
            .cast(pl.Int64)
            .alias(self._TS_COLUMN)
        )
        return df, df.height, 0

    def _sort_and_dedupe_timestamps(
        self,
        df: pl.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> pl.DataFrame:
        df = df.sort(self._TS_COLUMN)
        duplicates = int(df.get_column(self._TS_COLUMN).is_duplicated().sum())
        if not duplicates:
            return df
        df = df.unique(subset=[self._TS_COLUMN], keep="last").sort(self._TS_COLUMN)
        flags[self._FLAG_DUPLICATE_TS] = (
            flags.get(self._FLAG_DUPLICATE_TS, 0) + duplicates
        )
        warnings.append(f"dropped {duplicates} duplicate bars")
        return df

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

    def _timestamps_to_seconds(self, series: pl.Expr | pl.Series) -> pl.Expr | pl.Series:
        if isinstance(series, pl.Expr):
            return series.dt.timestamp("ms").floordiv(1000).cast(pl.Int64)
        return (series.dt.timestamp("ms") // 1000).cast(pl.Int64)

    def _normalize_integer_epoch(
        self,
        df: pl.DataFrame,
        flags: dict[str, int],
        warnings: list[str],
    ) -> tuple[int, pl.DataFrame]:
        ts = df.get_column(self._TS_COLUMN)
        invalid_count = int(ts.is_null().sum())
        if invalid_count:
            warnings.append(f"dropped {invalid_count} rows with invalid timestamps")
            flags[self._FLAG_INVALID_TS] = (
                flags.get(self._FLAG_INVALID_TS, 0) + invalid_count
            )
            df = df.filter(pl.col(self._TS_COLUMN).is_not_null())
            if df.is_empty():
                return 0, df
            ts = df.get_column(self._TS_COLUMN)

        normalized = ts.cast(pl.Int64, strict=False)
        divisor = self._infer_epoch_divisor(normalized)
        cast_rows = 0
        if divisor != 1:
            normalized = normalized // divisor
            cast_rows = df.height
        df = df.with_columns(normalized.alias(self._TS_COLUMN))
        return cast_rows, df

    def _infer_epoch_divisor(self, series: pl.Series) -> int:
        values = self._non_zero_epoch_values(series)
        if not values.size:
            return 1

        max_value = int(values.max())
        # Treat small magnitudes as already being in the desired resolution (seconds).
        # This prevents arbitrary integers such as [1_000, 4_000, ...] from being
        # interpreted as millisecond epochs and down-casted unexpectedly.
        if max_value < 10**10:
            return 1

        diff_divisor = self._candidate_divisor_from_diffs(values)
        if diff_divisor:
            return diff_divisor

        return self._divisor_from_magnitude(max_value)

    def _non_zero_epoch_values(self, series: pl.Series) -> NDArray[np.int64]:
        if len(series) == 0:
            return np.array([], dtype=np.int64)
        raw_values = series.to_numpy()
        values = cast(NDArray[np.int64], np.abs(raw_values, dtype=np.int64))
        if not values.size:
            return values
        return values[values > 0]

    def _candidate_divisor_from_diffs(self, values: np.ndarray) -> int | None:
        unique_sorted = np.unique(values)
        if unique_sorted.size < 2:
            return None
        diffs = np.diff(unique_sorted)
        positive_diffs = diffs[diffs > 0]
        if not positive_diffs.size:
            return None
        min_diff = int(positive_diffs.min())
        for divisor in (10**9, 10**6, 10**3):
            if min_diff % divisor == 0:
                return divisor
        return None

    @staticmethod
    def _divisor_from_magnitude(max_value: int) -> int:
        if max_value >= 10**16:
            return 10**9
        if max_value >= 10**13:
            return 10**6
        if max_value >= 10**10:
            return 10**3
        return 1


class TickConformanceRule:
    """Conformance rule for trade tick data validation.
    
    Validates that tick data has:
    - Required columns: ts, price, size
    - Positive prices and sizes
    - Sorted timestamps
    - Valid timestamp range
    
    Examples
    --------
    >>> rule = TickConformanceRule()
    >>> df = pl.DataFrame({
    ...     'ts': [1700000000, 1700000001],
    ...     'price': [100.0, 101.0],
    ...     'size': [1.0, 2.0],
    ... })
    >>> report = rule.validate(df)
    >>> len(report.warnings)
    0
    """
    
    REQUIRED_COLUMNS = frozenset({'ts', 'price', 'size'})
    OPTIONAL_COLUMNS = frozenset({'side', 'trade_id'})
    
    def validate(self, df: pl.DataFrame) -> ConformanceReport:
        """Validate tick data and return conformance report.
        
        Parameters
        ----------
        df
            Tick data DataFrame.
        
        Returns
        -------
        ConformanceReport
            Report with warnings and flag counts.
        """
        warnings: list[str] = []
        flags: dict[str, int] = {}
        
        # 1. Required columns
        missing = self.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            warnings.append(f"Missing required columns: {sorted(missing)}")
            flags['missing_column'] = len(missing)
            return ConformanceReport(warnings=tuple(warnings), flags_counts=flags)
        
        # 2. Price and Size validation
        self._check_positive_values(df, warnings, flags)
        self._check_nans(df, ['price', 'size'], warnings, flags)
        
        # 3. Temporal validation
        self._check_temporal_validity(df, warnings, flags)
        
        return ConformanceReport(warnings=tuple(warnings), flags_counts=flags)

    def _check_positive_values(self, df: pl.DataFrame, warnings: list[str], flags: dict[str, int]) -> None:
        """Check for non-positive prices and sizes."""
        for col, flag_key in [('price', 'invalid_price'), ('size', 'invalid_size')]:
            series = df.get_column(col)
            if (series <= 0).any():
                invalid_count = int((series <= 0).sum())
                warnings.append(f"Non-positive {col}s detected: {invalid_count} rows")
                flags[flag_key] = int(invalid_count)

    def _check_nans(self, df: pl.DataFrame, columns: list[str], warnings: list[str], flags: dict[str, int]) -> None:
        """Check for NaN values in specified columns."""
        for col in columns:
            series = df.get_column(col)
            nan_count = int(series.is_null().sum() + series.is_nan().sum())
            if nan_count:
                warnings.append(f"NaN values in {col}: {nan_count} rows")
                flags[f'nan_{col}'] = int(nan_count)

    def _check_temporal_validity(self, df: pl.DataFrame, warnings: list[str], flags: dict[str, int]) -> None:
        """Validate timestamp ordering, duplicates, and range."""
        # Ordering
        if not df.get_column("ts").is_sorted():
            warnings.append("Timestamps not sorted")
            flags['unsorted_ts'] = 1
        
        # Duplicates
        duplicates = int(df.get_column("ts").is_duplicated().sum())
        if duplicates > 0:
            warnings.append(f"Duplicate timestamps: {duplicates} rows")
            flags['duplicate_ts'] = int(duplicates)
        
        # Range (Unix epoch)
        ts_series = df.get_column("ts")
        invalid_ts_mask = (ts_series < 0) | (ts_series > 2**32 - 1)
        if invalid_ts_mask.any():
            invalid_count = int(invalid_ts_mask.sum())
            warnings.append(f"Invalid timestamp range: {invalid_count} rows")
            flags['invalid_timestamp'] = int(invalid_count)


class QuoteConformanceRule:
    """Conformance rule for quote tick data validation.
    
    Validates that quote data has:
    - Required columns: ts, bid, ask, bid_size, ask_size
    - Positive prices and sizes
    - Bid < Ask (no crossed quotes)
    - Sorted timestamps
    - Valid timestamp range
    
    Examples
    --------
    >>> rule = QuoteConformanceRule()
    >>> df = pl.DataFrame({
    ...     'ts': [1700000000],
    ...     'bid': [100.0],
    ...     'ask': [100.5],
    ...     'bid_size': [10.0],
    ...     'ask_size': [8.0],
    ... })
    >>> report = rule.validate(df)
    >>> len(report.warnings)
    0
    """
    
    REQUIRED_COLUMNS = frozenset({'ts', 'bid', 'ask', 'bid_size', 'ask_size'})
    OPTIONAL_COLUMNS = frozenset({'quote_id', 'venue_ts'})
    
    def validate(self, df: pl.DataFrame) -> ConformanceReport:
        """Validate quote data and return conformance report.
        
        Parameters
        ----------
        df
            Quote data DataFrame.
        
        Returns
        -------
        ConformanceReport
            Report with warnings and flag counts.
        """
        warnings: list[str] = []
        flags: dict[str, int] = {}
        
        # 1. Required columns
        missing = self.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            warnings.append(f"Missing required columns: {sorted(missing)}")
            flags['missing_column'] = len(missing)
            return ConformanceReport(warnings=tuple(warnings), flags_counts=flags)
        
        # 2. Spread and Price/Size validation
        self._check_quote_values(df, warnings, flags)
        self._check_nans(df, warnings, flags)
        
        # 3. Temporal validation
        self._check_temporal_validity(df, warnings, flags)
        
        return ConformanceReport(warnings=tuple(warnings), flags_counts=flags)

    def _check_quote_values(self, df: pl.DataFrame, warnings: list[str], flags: dict[str, int]) -> None:
        """Check for crossed quotes, non-positive values, and wide spreads."""
        # Bid/Ask spread
        crossed = int((df.get_column('bid') >= df.get_column('ask')).sum())
        if crossed > 0:
            warnings.append(f"Crossed quotes detected (bid >= ask): {crossed} rows")
            flags['crossed_quotes'] = int(crossed)
        
        # Positive values
        for col in ['bid', 'ask', 'bid_size', 'ask_size']:
            series = df.get_column(col)
            if (series <= 0).any():
                invalid_count = int((series <= 0).sum())
                warnings.append(f"Non-positive {col} values: {invalid_count} rows")
                flags[f'invalid_{col}'] = int(invalid_count)
        
        # Wide spreads
        spread_pct = ((df.get_column('ask') - df.get_column('bid')) / df.get_column('bid') * 100)
        wide_spreads = int((spread_pct > 10.0).sum())
        if wide_spreads > 0:
            warnings.append(f"Wide spreads (>10%): {wide_spreads} rows")
            flags['wide_spread'] = int(wide_spreads)

    def _check_nans(self, df: pl.DataFrame, warnings: list[str], flags: dict[str, int]) -> None:
        """Check for NaN values in all expected columns."""
        for col in ['bid', 'ask', 'bid_size', 'ask_size']:
            series = df.get_column(col)
            nan_count = int(series.is_null().sum() + series.is_nan().sum())
            if nan_count:
                warnings.append(f"NaN values in {col}: {nan_count} rows")
                flags[f'nan_{col}'] = int(nan_count)

    def _check_temporal_validity(self, df: pl.DataFrame, warnings: list[str], flags: dict[str, int]) -> None:
        """Validate timestamp ordering, duplicates, and range."""
        if not df.get_column("ts").is_sorted():
            warnings.append("Timestamps not sorted")
            flags['unsorted_ts'] = 1
        
        duplicates = int(df.get_column("ts").is_duplicated().sum())
        if duplicates > 0:
            warnings.append(f"Duplicate timestamps: {duplicates} rows")
            flags['duplicate_ts'] = int(duplicates)
        
        ts_series = df.get_column("ts")
        invalid_ts_mask = (ts_series < 0) | (ts_series > 2**32 - 1)
        if invalid_ts_mask.any():
            invalid_count = int(invalid_ts_mask.sum())
            warnings.append(f"Invalid timestamp range: {invalid_count} rows")
            flags['invalid_timestamp'] = int(invalid_count)


__all__ = [
    "ConformancePipeline",
    "ConformanceReport",
    "TickConformanceRule",
    "QuoteConformanceRule",
]


def _parse_polars_dtype(dtype: str) -> pl.DataType | None:
    lower = dtype.lower()
    if lower in {"float64", "float"}:
        return cast(pl.DataType, pl.Float64)
    if lower in {"float32"}:
        return cast(pl.DataType, pl.Float32)
    if lower in {"int64", "int"}:
        return cast(pl.DataType, pl.Int64)
    if lower in {"int32"}:
        return cast(pl.DataType, pl.Int32)
    if lower in {"int16"}:
        return cast(pl.DataType, pl.Int16)
    if lower in {"int8"}:
        return cast(pl.DataType, pl.Int8)
    if lower in {"uint64"}:
        return cast(pl.DataType, pl.UInt64)
    if lower in {"uint32"}:
        return cast(pl.DataType, pl.UInt32)
    if lower in {"uint16"}:
        return cast(pl.DataType, pl.UInt16)
    if lower in {"uint8"}:
        return cast(pl.DataType, pl.UInt8)
    if lower in {"utf8", "string", "str"}:
        return cast(pl.DataType, pl.Utf8)
    if dtype.startswith("Datetime("):
        time_unit = "ns"
        time_zone = None
        if "time_unit=" in dtype:
            time_unit = dtype.split("time_unit=")[1].split(",")[0].strip(" '\"")
        if "time_zone=" in dtype:
            time_zone = dtype.split("time_zone=")[1].split(")")[0].strip(" '\"")
        normalized_unit = time_unit if time_unit in {"ns", "us", "ms"} else "ns"
        return pl.Datetime(
            time_unit=cast(Literal["ns", "us", "ms"], normalized_unit),
            time_zone=time_zone,
        )
    if lower == "date":
        return cast(pl.DataType, pl.Date)
    return None


def _dtype_name(dtype: pl.DataType) -> str:
    return str(dtype)


def _is_float_dtype(dtype: pl.DataType) -> bool:
    return _dtype_name(dtype).startswith("Float")


def _is_integer_dtype(dtype: pl.DataType) -> bool:
    return _dtype_name(dtype).startswith("Int") or _dtype_name(dtype).startswith("UInt")


def _is_numeric_dtype(dtype: pl.DataType) -> bool:
    return _is_float_dtype(dtype) or _is_integer_dtype(dtype)


def _is_datetime_dtype(dtype: pl.DataType) -> bool:
    return _dtype_name(dtype).startswith("Datetime")
