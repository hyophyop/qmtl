from __future__ import annotations

import numpy as np
import pandas as pd

from qmtl.runtime.sdk.conformance import ConformancePipeline


def test_conformance_noop():
    df = pd.DataFrame({"ts": [1, 2, 3], "v": [10.0, 11.0, 12.0]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df.copy(), schema=None, interval=60)
    assert out.equals(df)
    assert report.warnings == ()
    assert report.flags_counts == {}


def test_conformance_drops_duplicates_and_reports():
    df = pd.DataFrame({"ts": [1, 2, 2, 3], "v": [10.0, 11.0, 12.5, 13.0]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=1)

    assert list(out["ts"]) == [1, 2, 3]
    # Last duplicate wins to preserve most recent write semantics
    assert np.isclose(out.loc[out["ts"] == 2, "v"].iloc[0], 12.5)
    assert report.flags_counts["duplicate_ts"] == 1
    assert any("duplicate" in warning for warning in report.warnings)


def test_conformance_detects_missing_gaps():
    df = pd.DataFrame({"ts": [1_000, 4_000, 7_000], "v": [1, 2, 3]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=1_000)

    assert list(out["ts"]) == [1_000, 4_000, 7_000]
    assert report.flags_counts["gap"] == 4  # two gaps, each with two bars missing
    assert any("missing bars" in warning for warning in report.warnings)


def test_conformance_schema_casts_and_reports():
    df = pd.DataFrame({"ts": [1, 2], "price": [1, 2]})
    cp = ConformancePipeline()
    schema = {"ts": "int64", "price": "float64"}
    out, report = cp.normalize(df, schema=schema, interval=1)

    assert str(out["price"].dtype) == "float64"
    assert report.flags_counts["dtype_cast"] == 1


def test_conformance_handles_field_style_schema():
    df = pd.DataFrame({"ts": [1, 2], "price": [1.0, 2.0]})
    schema = {"fields": [{"name": "ts", "dtype": "int64"}, {"name": "price", "dtype": "float64"}]}
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=schema, interval=1)

    assert out.equals(df)
    assert report.warnings == ()


def test_conformance_warns_without_ts_column():
    df = pd.DataFrame({"price": [1.0, 2.0]})
    cp = ConformancePipeline()
    _, report = cp.normalize(df, schema=None, interval=1)

    assert "missing ts column" in report.warnings[0]


def test_conformance_normalizes_timezone_and_flags_casts():
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2025-01-01T00:00:00+02:00",
                    "2025-01-01T00:01:00+02:00",
                ]
            ),
            "price": [1.0, 2.0],
        }
    )

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    assert pd.api.types.is_integer_dtype(out["ts"].dtype)
    assert out["ts"].tolist() == [1735682400, 1735682460]
    assert report.flags_counts["ts_cast"] == 2
    assert report.flags_counts["ts_timezone_normalized"] == 2


def test_conformance_casts_flexible_timestamps_without_relying_on_index_alignment():
    base = pd.Timestamp("2025-01-01T00:00:00Z")
    df = pd.DataFrame(
        {
            "ts": [
                (base + pd.Timedelta(minutes=offset)).isoformat()
                for offset in (0, 1, 2)
            ],
            "price": [1.0, 2.0, 3.0],
        },
        index=[10, 20, 30],
    )

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [
        int((base + pd.Timedelta(minutes=offset)).value // 10**9)
        for offset in (0, 1, 2)
    ]
    assert out["ts"].tolist() == expected
    assert report.flags_counts["ts_cast"] == 3


def test_conformance_normalizes_non_finite_values():
    df = pd.DataFrame(
        {
            "ts": [0, 1, 2],
            "price": [1.0, np.inf, np.nan],
        }
    )

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=None)

    assert pd.isna(out.loc[1, "price"])
    assert pd.isna(out.loc[2, "price"])
    assert report.flags_counts["non_finite"] == 2
    assert any("inf" in warning for warning in report.warnings)


def test_conformance_normalizes_integer_epoch_units():
    base = pd.Timestamp("2025-01-01T00:00:00Z")
    ns_values = [base.value, base.value + 60 * 10**9, base.value + 120 * 10**9]
    df = pd.DataFrame({"ts": ns_values, "price": [1.0, 2.0, 3.0]})

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int(base.value // 10**9) + offset for offset in (0, 60, 120)]
    assert out["ts"].tolist() == expected
    assert report.flags_counts["ts_cast"] == 3


def test_conformance_normalizes_millisecond_epoch_units():
    base = pd.Timestamp("2025-01-01T00:00:00Z")
    ms_values = [
        base.value // 10**6,
        base.value // 10**6 + 60 * 1000,
        base.value // 10**6 + 120 * 1000,
    ]
    df = pd.DataFrame({"ts": ms_values, "price": [1.0, 2.0, 3.0]})

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int(base.value // 10**9) + offset for offset in (0, 60, 120)]
    assert out["ts"].tolist() == expected
    assert report.flags_counts["ts_cast"] == 3


def test_conformance_normalizes_microsecond_epochs_near_epoch_start():
    base = pd.Timestamp("1971-01-01T00:00:00Z")
    micro_values = [
        base.value // 10**3,
        base.value // 10**3 + 60 * 10**6,
        base.value // 10**3 + 120 * 10**6,
    ]
    df = pd.DataFrame({"ts": micro_values, "price": [1.0, 2.0, 3.0]})

    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=60)

    expected = [int(base.value // 10**9) + offset for offset in (0, 60, 120)]
    assert out["ts"].tolist() == expected
    assert report.flags_counts["ts_cast"] == 3
