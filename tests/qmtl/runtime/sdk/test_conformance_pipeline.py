from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import numpy as np
import polars as pl
from polars.testing import assert_frame_equal

from qmtl.runtime.sdk.conformance import ConformancePipeline


def test_conformance_noop():
    df = pl.DataFrame({"ts": [1, 2, 3], "v": [10.0, 11.0, 12.0]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df.clone(), schema=None, interval=60)
    assert_frame_equal(out, df)
    assert report.warnings == ()
    assert report.flags_counts == {}


def test_conformance_drops_duplicates_and_reports():
    df = pl.DataFrame({"ts": [1, 2, 2, 3], "v": [10.0, 11.0, 12.5, 13.0]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=1)

    assert out.get_column("ts").to_list() == [1, 2, 3]
    # Last duplicate wins to preserve most recent write semantics
    v_values = out.filter(pl.col("ts") == 2).get_column("v").to_list()
    assert np.isclose(v_values[0], 12.5)
    assert report.flags_counts["duplicate_ts"] == 2
    assert any("duplicate" in warning for warning in report.warnings)


def test_conformance_detects_missing_gaps():
    df = pl.DataFrame({"ts": [1_000, 4_000, 7_000], "v": [1, 2, 3]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=1_000)

    assert out.get_column("ts").to_list() == [1_000, 4_000, 7_000]
    assert report.flags_counts["gap"] == 4  # two gaps, each with two bars missing
    assert any("missing bars" in warning for warning in report.warnings)


def test_conformance_schema_casts_and_reports():
    df = pl.DataFrame({"ts": [1, 2], "price": [1, 2]})
    cp = ConformancePipeline()
    schema = {"ts": "Int64", "price": "Float64"}
    out, report = cp.normalize(df, schema=schema, interval=1)

    assert str(out.schema.get("price")) == "Float64"
    assert report.flags_counts["dtype_cast"] == 1


def test_conformance_handles_field_style_schema():
    df = pl.DataFrame({"ts": [1, 2], "price": [1.0, 2.0]})
    schema = {"fields": [{"name": "ts", "dtype": "Int64"}, {"name": "price", "dtype": "Float64"}]}
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=schema, interval=1)

    assert_frame_equal(out, df)
    assert report.warnings == ()


def test_conformance_warns_without_ts_column():
    df = pl.DataFrame({"price": [1.0, 2.0]})
    cp = ConformancePipeline()
    _, report = cp.normalize(df, schema=None, interval=1)

    assert "missing ts column" in report.warnings[0]


def test_conformance_normalizes_timezone_and_flags_casts():
    df = pl.DataFrame(
        {
            "ts": [
                datetime.fromisoformat("2025-01-01T00:00:00+02:00"),
                datetime.fromisoformat("2025-01-01T00:01:00+02:00"),
            ],
            "price": [1.0, 2.0],
        }
    )

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    assert str(out.schema.get("ts")) == "Int64"
    assert out.get_column("ts").to_list() == [1735682400, 1735682460]
    assert report.flags_counts["ts_cast"] == 2
    assert report.flags_counts["ts_timezone_normalized"] == 2


def test_conformance_casts_flexible_timestamps_without_relying_on_index_alignment():
    base = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    df = pl.DataFrame(
        {
            "ts": [
                (base + timedelta(minutes=offset)).isoformat()
                for offset in (0, 1, 2)
            ],
            "price": [1.0, 2.0, 3.0],
        },
    )

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int((base + timedelta(minutes=offset)).timestamp()) for offset in (0, 1, 2)]
    assert out.get_column("ts").to_list() == expected
    assert report.flags_counts["ts_cast"] == 3


def test_conformance_normalizes_non_finite_values():
    df = pl.DataFrame(
        {
            "ts": [0, 1, 2],
            "price": [1.0, np.inf, np.nan],
        }
    )

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=None)

    prices = out.get_column("price").to_list()
    assert prices[1] is None or (isinstance(prices[1], float) and math.isnan(prices[1]))
    assert prices[2] is None or (isinstance(prices[2], float) and math.isnan(prices[2]))
    assert report.flags_counts["non_finite"] == 2
    assert any("inf" in warning for warning in report.warnings)


def test_conformance_normalizes_integer_epoch_units():
    base = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    base_ns = int(base.timestamp() * 10**9)
    ns_values = [base_ns, base_ns + 60 * 10**9, base_ns + 120 * 10**9]
    df = pl.DataFrame({"ts": ns_values, "price": [1.0, 2.0, 3.0]})

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int(base.timestamp()) + offset for offset in (0, 60, 120)]
    assert out.get_column("ts").to_list() == expected
    assert report.flags_counts["ts_cast"] == 3


def test_conformance_normalizes_millisecond_epoch_units():
    base = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    base_ns = int(base.timestamp() * 10**9)
    ms_values = [
        base_ns // 10**6,
        base_ns // 10**6 + 60 * 1000,
        base_ns // 10**6 + 120 * 1000,
    ]
    df = pl.DataFrame({"ts": ms_values, "price": [1.0, 2.0, 3.0]})

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int(base.timestamp()) + offset for offset in (0, 60, 120)]
    assert out.get_column("ts").to_list() == expected
    assert report.flags_counts["ts_cast"] == 3


def test_conformance_normalizes_microsecond_epochs_near_epoch_start():
    base = datetime(1971, 1, 1, 0, 0, tzinfo=timezone.utc)
    base_ns = int(base.timestamp() * 10**9)
    micro_values = [
        base_ns // 10**3,
        base_ns // 10**3 + 60 * 10**6,
        base_ns // 10**3 + 120 * 10**6,
    ]
    df = pl.DataFrame({"ts": micro_values, "price": [1.0, 2.0, 3.0]})

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int(base.timestamp()) + offset for offset in (0, 60, 120)]
    assert out.get_column("ts").to_list() == expected
    assert report.flags_counts["ts_cast"] == 3
