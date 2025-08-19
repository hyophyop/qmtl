import pandas as pd
import pytest
from qmtl.io import QuestDBRecorder, QuestDBLoader


@pytest.mark.asyncio
async def test_questdb_roundtrip(monkeypatch) -> None:
    storage: list[dict] = []

    async def fake_persist(self, node_id, interval, timestamp, payload):
        storage.append({"node_id": node_id, "interval": interval, "ts": timestamp, **payload})

    async def fake_fetch(self, start, end, *, node_id, interval):
        rows = [
            row
            for row in storage
            if row["node_id"] == node_id
            and row["interval"] == interval
            and start <= row["ts"] < end
        ]
        return pd.DataFrame(rows)

    monkeypatch.setattr(QuestDBRecorder, "persist", fake_persist)
    monkeypatch.setattr(QuestDBLoader, "fetch", fake_fetch)

    recorder = QuestDBRecorder(dsn="memory")
    loader = QuestDBLoader(dsn="memory")

    await recorder.persist("n", 60, 0, {"price": 1.0})
    df = await loader.fetch(0, 1, node_id="n", interval=60)

    assert not df.empty
    assert df.iloc[0]["price"] == 1.0
