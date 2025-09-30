import pandas as pd
import pytest

from qmtl.runtime.io.seamless_provider import (
    EnhancedQuestDBProvider,
    EnhancedQuestDBProviderSettings,
    FingerprintPolicy,
)
from qmtl.runtime.sdk.conformance import ConformancePipeline
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy
from qmtl.runtime.sdk.sla import SLAPolicy


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

    settings = EnhancedQuestDBProviderSettings(
        registrar=_RegistrarStub(),
        node_id_format="ohlcv:{exchange}:{symbol}:{timeframe}",
        strategy=DataAvailabilityStrategy.FAIL_FAST,
    )

    provider = EnhancedQuestDBProvider("memory://", settings=settings)

    # Invalid OHLCV identifier should fail fast before hitting storage.
    with pytest.raises(ValueError):
        await provider.fetch(0, 60, node_id="ohlcv:binance:BTC/USDT", interval=60)

    # Well-formed identifier is accepted.
    df = await provider.fetch(0, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df.empty or "ts" in df.columns


@pytest.mark.asyncio
async def test_enhanced_provider_settings_apply_policies(monkeypatch):
    monkeypatch.setattr(
        "qmtl.runtime.io.historyprovider.QuestDBLoader",
        _QuestDBLoaderStub,
    )

    custom_conformance = ConformancePipeline()
    custom_sla = SLAPolicy(total_deadline_ms=5000)

    settings = EnhancedQuestDBProviderSettings(
        registrar=_RegistrarStub(),
        conformance=custom_conformance,
        sla=custom_sla,
        fingerprint=FingerprintPolicy(publish=True, early=False),
    )

    provider = EnhancedQuestDBProvider("memory://", settings=settings)

    assert provider.strategy == settings.strategy
    assert provider._conformance is custom_conformance
    assert provider._sla is custom_sla
    assert provider._publish_fingerprint is True
    assert provider._early_fingerprint is False

    provider_override = EnhancedQuestDBProvider(
        "memory://",
        settings=settings,
        publish_fingerprint=False,
        early_fingerprint=True,
    )

    assert provider_override._publish_fingerprint is False
    assert provider_override._early_fingerprint is True
