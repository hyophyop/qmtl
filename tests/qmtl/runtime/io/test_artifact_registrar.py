import pandas as pd
import pytest

from qmtl.runtime.io.artifact import ArtifactRegistrar


@pytest.mark.asyncio
async def test_publish_stabilizes_frame_and_records_manifest():
    captured: dict[str, object] = {}

    def fake_store(frame: pd.DataFrame, manifest: dict):
        captured["frame"] = frame.copy(deep=True)
        captured["manifest"] = dict(manifest)
        return "memory://artifact"

    registrar = ArtifactRegistrar(store=fake_store, stabilization_bars=1, producer_identity=" tester ")
    frame = pd.DataFrame(
        [
            {"ts": 10, "open": 100, "close": 101, "volume": 1.5},
            {"ts": 20, "open": 102, "close": 103, "volume": 1.7},
        ]
    )

    publication = await registrar.publish(
        frame,
        node_id="alpha.node",
        interval=60,
        requested_range=(10, 20),
    )

    assert publication is not None
    assert publication.uri == "memory://artifact"
    assert publication.rows == 1
    assert publication.start == 10
    assert publication.end == 10
    assert publication.manifest["producer"]["identity"] == "tester"
    assert captured["frame"].shape == (1, 4)
    assert captured["manifest"]["requested_range"] == [10, 20]


@pytest.mark.asyncio
async def test_publish_returns_none_when_frame_missing_timestamp():
    registrar = ArtifactRegistrar()
    frame = pd.DataFrame([{"open": 100, "close": 101}])

    result = await registrar.publish(frame, node_id="alpha.node", interval=60)

    assert result is None
