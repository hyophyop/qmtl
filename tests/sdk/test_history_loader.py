import pytest

from qmtl.sdk import Strategy, StreamInput
from qmtl.sdk.history_loader import HistoryLoader


class _Strat(Strategy):
    def setup(self):
        self.src = StreamInput(interval="60s", period=2)
        self.add_nodes([self.src])


@pytest.mark.asyncio
async def test_history_loader_calls_nodes(monkeypatch):
    strat = _Strat()
    strat.setup()
    called = []

    async def fake_load_history(self, start, end):
        called.append((start, end))

    monkeypatch.setattr(StreamInput, "load_history", fake_load_history)
    await HistoryLoader.load(strat, 1, 2)
    assert called == [(1, 2)]
