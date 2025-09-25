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
    assert report.flags_counts["duplicate_bars"] == 1
    assert any("duplicate" in warning for warning in report.warnings)


def test_conformance_detects_missing_gaps():
    df = pd.DataFrame({"ts": [1_000, 4_000, 7_000], "v": [1, 2, 3]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df, schema=None, interval=1_000)

    assert list(out["ts"]) == [1_000, 4_000, 7_000]
    assert report.flags_counts["missing_bars"] == 4  # two gaps, each with two bars missing
    assert any("interval gaps" in warning for warning in report.warnings)


def test_conformance_schema_casts_and_reports():
    df = pd.DataFrame({"ts": [1, 2], "price": [1, 2]})
    cp = ConformancePipeline()
    schema = {"ts": "int64", "price": "float64"}
    out, report = cp.normalize(df, schema=schema, interval=1)

    assert str(out["price"].dtype) == "float64"
    assert report.flags_counts["dtype_casts"] == 1


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
