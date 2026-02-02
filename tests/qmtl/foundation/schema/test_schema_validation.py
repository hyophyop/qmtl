from datetime import datetime, timezone
import polars as pl
import pytest

from qmtl.foundation.schema import validate_schema
from qmtl.runtime.sdk.exceptions import InvalidSchemaError


def test_missing_column_raises_friendly_error():
    df = pl.DataFrame(
        {
            "ts": pl.Series(
                "ts",
                [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                dtype=pl.Datetime(time_unit="ns", time_zone="UTC"),
            ),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            # volume column intentionally omitted
        }
    )

    with pytest.raises(InvalidSchemaError) as exc:
        validate_schema(df, "bar")
    assert "missing columns: volume" in str(exc.value)


def test_valid_bar_schema_passes():
    df = pl.DataFrame(
        {
            "ts": pl.Series(
                "ts",
                [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                dtype=pl.Datetime(time_unit="ns", time_zone="UTC"),
            ),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        }
    )

    validate_schema(df, "bar")  # should not raise
