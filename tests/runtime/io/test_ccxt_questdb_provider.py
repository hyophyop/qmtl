from __future__ import annotations

import pandas as pd
import pytest

from qmtl.runtime.io import CcxtQuestDBProvider
from qmtl.runtime.io.ccxt_fetcher import CcxtBackfillConfig, CcxtOHLCVFetcher


class _InMemoryBackend:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, int], dict[int, dict]] = {}

    async def read_range(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        table = self._rows.get((node_id, interval), {})
        data = []
        for ts in sorted(table):
            if start <= ts < end:
                row = {"ts": ts}
                row.update(table[ts])
                data.append(row)
        return pd.DataFrame(data)

    async def write_rows(self, rows: pd.DataFrame, *, node_id: str, interval: int) -> None:
        if rows is None or rows.empty:
            return
        table = self._rows.setdefault((node_id, interval), {})
        for rec in rows.to_dict("records"):
            ts = int(rec["ts"])
            payload = {k: v for k, v in rec.items() if k != "ts"}
            table[ts] = payload

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        table = self._rows.get((node_id, interval), {})
        timestamps = sorted(table)
        if not timestamps:
            return []
        ranges: list[tuple[int, int]] = []
        start = prev = timestamps[0]
        for ts in timestamps[1:]:
            if ts == prev + interval:
                prev = ts
            else:
                ranges.append((start, prev))
                start = prev = ts
        ranges.append((start, prev))
        return ranges


class _StubExchange:
    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        # Return a single aligned candle at 60s
        return [[60_000, 1, 1, 1, 1, 1]]

    async def close(self):  # pragma: no cover
        pass


@pytest.mark.asyncio
async def test_ccxt_questdb_provider_wiring_and_backfill(monkeypatch):
    # Build provider with injected fetcher
    fetcher = CcxtOHLCVFetcher(CcxtBackfillConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
    ), exchange=_StubExchange())

    provider = CcxtQuestDBProvider("db", table="node_data", fetcher=fetcher)
    # Swap backend to in-memory for the test
    backend = _InMemoryBackend()
    provider.backend = backend  # type: ignore[attr-defined]

    # Trigger backfill
    await provider.fill_missing(60, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)

    # Verify data materialized
    df = await backend.read_range(0, 120, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df["ts"].tolist() == [60]


def _base_provider_config(**rate_limiter: object) -> dict[str, object]:
    return {
        "exchange": "binance",
        "symbols": ["BTC/USDT"],
        "timeframe": "1m",
        "questdb": {
            "dsn": "postgresql://localhost:8812/qdb",
            "table": "crypto_ohlcv",
        },
        "rate_limiter": rate_limiter,
    }


def test_from_config_accepts_min_interval_ms():
    cfg = _base_provider_config(min_interval_ms=25)
    provider = CcxtQuestDBProvider.from_config(cfg)
    assert provider.fetcher is not None  # sanity check
    limiter = provider.fetcher.config.rate_limiter  # type: ignore[union-attr]
    assert limiter.min_interval_s == pytest.approx(0.025)


def test_from_config_allows_matching_min_interval_fields():
    cfg = _base_provider_config(min_interval_ms=250, min_interval_s=0.25)
    provider = CcxtQuestDBProvider.from_config(cfg)
    limiter = provider.fetcher.config.rate_limiter  # type: ignore[union-attr]
    assert limiter.min_interval_s == pytest.approx(0.25)


def test_from_config_rejects_conflicting_min_interval_fields():
    cfg = _base_provider_config(min_interval_ms=300, min_interval_s=0.1)
    with pytest.raises(ValueError):
        CcxtQuestDBProvider.from_config(cfg)


def test_from_config_propagates_key_template():
    cfg = _base_provider_config(
        key_suffix="acct42",
        key_template="ccxt:{exchange}:{suffix}",
    )
    provider = CcxtQuestDBProvider.from_config(cfg)
    fetcher = provider.fetcher
    assert fetcher is not None
    rl = fetcher.config.rate_limiter  # type: ignore[union-attr]
    assert rl.key_template == "ccxt:{exchange}:{suffix}"
    assert rl.key_suffix == "acct42"

