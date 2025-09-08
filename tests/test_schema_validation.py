import pandas as pd
import pytest

from qmtl.schema import validate_schema
from qmtl.sdk.exceptions import InvalidSchemaError


def test_missing_column_raises_friendly_error():
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=1, tz="UTC"),
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
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=1, tz="UTC"),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        }
    )

    validate_schema(df, "bar")  # should not raise

