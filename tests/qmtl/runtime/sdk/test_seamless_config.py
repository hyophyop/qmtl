from __future__ import annotations

import pytest

import pandas as pd

from qmtl.runtime.sdk import build_seamless_assembly, hydrate_builder
from qmtl.runtime.sdk.seamless_data_provider import DataSourcePriority
from qmtl.runtime.io.seamless_provider import (
    HistoryProviderDataSource,
    DataFetcherAutoBackfiller,
)


def _ccxt_preset_config() -> dict:
    return {
        "preset": "ccxt.questdb.ohlcv",
        "options": {
            "exchange_id": "binance",
            "symbols": ["BTC/USDT"],
            "timeframe": "1m",
            "questdb": {
                "dsn": "postgresql://localhost:8812/qdb",
                "table": "crypto_ohlcv",
            },
        },
    }


def test_build_seamless_assembly_from_single_preset() -> None:
    assembly = build_seamless_assembly(_ccxt_preset_config())

    assert isinstance(assembly.storage_source, HistoryProviderDataSource)
    assert assembly.storage_source.priority is DataSourcePriority.STORAGE
    assert isinstance(assembly.backfiller, DataFetcherAutoBackfiller)
    assert assembly.cache_source is None
    assert assembly.live_feed is None
    assert assembly.registrar is None


def test_hydrate_builder_supports_presets_sequence() -> None:
    config = {
        "presets": [
            {
                "name": "ccxt.questdb.ohlcv",
                "options": _ccxt_preset_config()["options"],
            }
        ]
    }

    builder = hydrate_builder(config)
    assembly = builder.build()

    assert isinstance(assembly.storage_source, HistoryProviderDataSource)
    assert assembly.storage_source.priority is DataSourcePriority.STORAGE
    assert isinstance(assembly.backfiller, DataFetcherAutoBackfiller)


def test_unknown_preset_raises_key_error() -> None:
    with pytest.raises(KeyError):
        build_seamless_assembly({"preset": "unknown.preset"})


def test_preset_assembly_uses_loader_and_fetcher(monkeypatch) -> None:
    created = {}

    class FakeFetcher:
        def __init__(self, config):
            created["fetcher_config"] = config

    class FakeLoader:
        def __init__(self, dsn, *, table=None, fetcher=None):
            created["loader_args"] = {
                "dsn": dsn,
                "table": table,
                "fetcher": fetcher,
            }

        async def fetch(self, start, end, *, node_id, interval):
            return pd.DataFrame()

        async def coverage(self, *, node_id, interval):
            return []

        async def fill_missing(self, start, end, *, node_id, interval):
            return None

    monkeypatch.setattr(
        "qmtl.runtime.io.seamless_presets.CcxtOHLCVFetcher",
        FakeFetcher,
    )
    monkeypatch.setattr(
        "qmtl.runtime.io.seamless_presets.QuestDBLoader",
        FakeLoader,
    )

    assembly = build_seamless_assembly(_ccxt_preset_config())

    assert isinstance(assembly.storage_source, HistoryProviderDataSource)
    assert assembly.storage_source.priority is DataSourcePriority.STORAGE
    assert isinstance(assembly.backfiller, DataFetcherAutoBackfiller)
    assert "loader_args" in created
    assert created["loader_args"]["dsn"] == "postgresql://localhost:8812/qdb"
    assert created["loader_args"]["table"] == "crypto_ohlcv"
    assert isinstance(created["loader_args"]["fetcher"], FakeFetcher)
    assert created["fetcher_config"].exchange_id == "binance"
