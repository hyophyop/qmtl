from __future__ import annotations

import pandas as pd
import pytest

from qmtl.runtime.io.seamless_provider import InMemorySeamlessProvider
from qmtl.runtime.sdk import StreamInput


def _make_frame(ts_values: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"ts": ts_values, "v": list(range(len(ts_values)))})


@pytest.mark.asyncio
async def test_inmemory_provider_register_and_fetch() -> None:
    provider = InMemorySeamlessProvider()
    stream = StreamInput(interval="60s", period=2)

    frame = _make_frame([60, 120, 180])
    provider.register_frame(stream, frame)

    df = await provider.fetch(60, 181, node_id=stream.node_id, interval=60)
    assert df["ts"].tolist() == [60, 120, 180]

    cov = await provider.coverage(node_id=stream.node_id, interval=60)
    assert cov == [(60, 180)]


@pytest.mark.asyncio
async def test_inmemory_provider_register_csv(tmp_path) -> None:
    provider = InMemorySeamlessProvider()
    stream = StreamInput(interval="60s", period=2)

    frame = _make_frame([60, 120])
    path = tmp_path / "history.csv"
    frame.to_csv(path, index=False)

    provider.register_csv(stream, path)

    df = await provider.fetch(60, 180, node_id=stream.node_id, interval=60)
    assert df["ts"].tolist() == [60, 120]

