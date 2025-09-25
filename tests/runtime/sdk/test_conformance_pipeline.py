from __future__ import annotations

import pandas as pd

from qmtl.runtime.sdk.conformance import ConformancePipeline


def test_conformance_noop():
    df = pd.DataFrame({"ts": [1, 2, 3], "v": [10.0, 11.0, 12.0]})
    cp = ConformancePipeline()
    out, report = cp.normalize(df.copy(), schema=None, interval=60)
    assert out.equals(df)
    assert report.warnings == ()
