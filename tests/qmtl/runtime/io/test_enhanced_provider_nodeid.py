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
        self.fetch_calls = 0

    async def fetch(self, start, end, *, node_id: str, interval: int) -> pd.DataFrame:
        self.fetch_calls += 1
        frame = pd.DataFrame(
            {
                "ts": pd.Series([start], dtype="int64"),
                "open": [1.0],
                "high": [1.5],
                "low": [0.9],
                "close": [1.2],
                "volume": [123.0],
            }
        )
        return frame

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
        partial_ok=True,
    )

    provider = EnhancedQuestDBProvider("memory://", settings=settings)
    storage = provider.storage_provider

    # Invalid OHLCV identifier should fail fast before hitting storage.
    with pytest.raises(ValueError):
        await provider.fetch(0, 60, node_id="ohlcv:binance:BTC/USDT", interval=60)
    assert getattr(storage, "fetch_calls", 0) == 0

    # Well-formed identifier is accepted.
    df = await provider.fetch(0, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df.empty or "ts" in df.columns
    assert storage.fetch_calls == 1


@pytest.mark.asyncio
async def test_enhanced_provider_settings_apply_policies(monkeypatch):
    monkeypatch.setattr(
        "qmtl.runtime.io.historyprovider.QuestDBLoader",
        _QuestDBLoaderStub,
    )

    recorded_calls: list[dict[str, object]] = []

    def _seamless_init_stub(
        self,
        *,
        strategy,
        cache_source=None,
        storage_source=None,
        backfiller=None,
        live_feed=None,
        conformance=None,
        partial_ok=None,
        registrar=None,
        **kwargs,
    ):
        recorded_calls.append(
            {
                "conformance": conformance,
                "sla": kwargs.get("sla"),
                "publish_fingerprint": kwargs.get("publish_fingerprint"),
                "early_fingerprint": kwargs.get("early_fingerprint"),
            }
        )

        # Minimal attribute initialization expected by tests and downstream usage.
        self.strategy = strategy
        self.cache_source = cache_source
        self.storage_source = storage_source
        self.backfiller = backfiller
        self.live_feed = live_feed
        self.partial_ok = partial_ok
        self.registrar = registrar

    monkeypatch.setattr(
        "qmtl.runtime.sdk.seamless_data_provider.SeamlessDataProvider.__init__",
        _seamless_init_stub,
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
    assert recorded_calls[-1]["conformance"] is custom_conformance
    assert recorded_calls[-1]["sla"] is custom_sla
    assert recorded_calls[-1]["publish_fingerprint"] is True
    assert recorded_calls[-1]["early_fingerprint"] is False

    provider_override = EnhancedQuestDBProvider(
        "memory://",
        settings=settings,
        publish_fingerprint=False,
        early_fingerprint=True,
    )

    assert recorded_calls[-1]["publish_fingerprint"] is False
    assert recorded_calls[-1]["early_fingerprint"] is True
