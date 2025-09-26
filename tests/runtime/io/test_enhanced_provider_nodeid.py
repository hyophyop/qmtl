import pandas as pd
import pytest

from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy


class _QuestDBLoaderStub:
    def __init__(self, dsn, table=None, fetcher=None):
        self.dsn = dsn
        self.table = table
        self.fetcher = fetcher

    async def fetch(self, start, end, *, node_id: str, interval: int) -> pd.DataFrame:
        return pd.DataFrame({"ts": [start]})

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        return [(0, 10_000_000)]

    def bind_stream(self, stream) -> None:  # pragma: no cover - not used in tests
        self._stream = stream


class _RegistrarStub:
    def publish(self, *args, **kwargs):  # pragma: no cover - publication not awaited in tests
        return None


@pytest.mark.asyncio
async def test_enhanced_provider_validates_node_ids(monkeypatch):
    monkeypatch.setattr(
        "qmtl.runtime.io.historyprovider.QuestDBLoader",
        _QuestDBLoaderStub,
    )

    provider = EnhancedQuestDBProvider(
        "memory://",
        registrar=_RegistrarStub(),
        node_id_format="ohlcv:{exchange}:{symbol}:{timeframe}",
        strategy=DataAvailabilityStrategy.FAIL_FAST,
    )

    # Invalid OHLCV identifier should fail fast before hitting storage.
    with pytest.raises(ValueError):
        await provider.fetch(0, 60, node_id="ohlcv:binance:BTC/USDT", interval=60)

    # Well-formed identifier is accepted.
    df = await provider.fetch(0, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df.empty or "ts" in df.columns
