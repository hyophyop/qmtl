"""Data fetching and persistence helpers."""

from __future__ import annotations

import importlib

__all__ = [
    "DataFetcher",
    "HistoryProvider",
    "QuestDBBackend",
    "QuestDBHistoryProvider",
    "QuestDBLoader",
    "EventRecorder",
    "QuestDBRecorder",
    "BinanceFetcher",
    "EnhancedQuestDBProvider",
    "EnhancedQuestDBProviderSettings",
    "FingerprintPolicy",
    "InMemorySeamlessProvider",
    "CcxtBackfillConfig",
    "RateLimiterConfig",
    "CcxtOHLCVFetcher",
    "CcxtTradesConfig",
    "CcxtTradesFetcher",
    "CcxtQuestDBProvider",
    "CcxtProLiveFeed",
    "CcxtProConfig",
    "ArtifactRegistrar",
    "ArtifactPublication",
    # Nautilus Trader integration
    "NautilusCatalogDataSource",
    "NautilusCoverageIndex",
    "NautilusPresetUnavailableError",
    "NautilusCatalogNotFoundError",
]

_ATTR_MAP = {
    "DataFetcher": ("qmtl.runtime.io.datafetcher", "DataFetcher"),
    "HistoryProvider": ("qmtl.runtime.sdk.data_io", "HistoryProvider"),
    "EventRecorder": ("qmtl.runtime.sdk.data_io", "EventRecorder"),
    "QuestDBBackend": ("qmtl.runtime.io.historyprovider", "QuestDBBackend"),
    "QuestDBHistoryProvider": ("qmtl.runtime.io.historyprovider", "QuestDBHistoryProvider"),
    "QuestDBLoader": ("qmtl.runtime.io.historyprovider", "QuestDBLoader"),
    "QuestDBRecorder": ("qmtl.runtime.io.eventrecorder", "QuestDBRecorder"),
    "BinanceFetcher": ("qmtl.runtime.io.binance_fetcher", "BinanceFetcher"),
    "EnhancedQuestDBProvider": ("qmtl.runtime.io.seamless_provider", "EnhancedQuestDBProvider"),
    "EnhancedQuestDBProviderSettings": ("qmtl.runtime.io.seamless_provider", "EnhancedQuestDBProviderSettings"),
    "FingerprintPolicy": ("qmtl.runtime.io.seamless_provider", "FingerprintPolicy"),
    "InMemorySeamlessProvider": ("qmtl.runtime.io.seamless_provider", "InMemorySeamlessProvider"),
    "CcxtBackfillConfig": ("qmtl.runtime.io.ccxt_fetcher", "CcxtBackfillConfig"),
    "RateLimiterConfig": ("qmtl.runtime.io.ccxt_fetcher", "RateLimiterConfig"),
    "CcxtOHLCVFetcher": ("qmtl.runtime.io.ccxt_fetcher", "CcxtOHLCVFetcher"),
    "CcxtTradesConfig": ("qmtl.runtime.io.ccxt_fetcher", "CcxtTradesConfig"),
    "CcxtTradesFetcher": ("qmtl.runtime.io.ccxt_fetcher", "CcxtTradesFetcher"),
    "CcxtQuestDBProvider": ("qmtl.runtime.io.ccxt_provider", "CcxtQuestDBProvider"),
    "CcxtProLiveFeed": ("qmtl.runtime.io.ccxt_live_feed", "CcxtProLiveFeed"),
    "CcxtProConfig": ("qmtl.runtime.io.ccxt_live_feed", "CcxtProConfig"),
    "ArtifactRegistrar": ("qmtl.runtime.io.artifact", "ArtifactRegistrar"),
    "ArtifactPublication": ("qmtl.runtime.io.artifact", "ArtifactPublication"),
    # Nautilus Trader integration
    "NautilusCatalogDataSource": ("qmtl.runtime.io.nautilus_catalog_source", "NautilusCatalogDataSource"),
    "NautilusCoverageIndex": ("qmtl.runtime.io.nautilus_coverage_index", "NautilusCoverageIndex"),
    "NautilusPresetUnavailableError": ("qmtl.runtime.io.seamless_presets", "NautilusPresetUnavailableError"),
    "NautilusCatalogNotFoundError": ("qmtl.runtime.io.seamless_presets", "NautilusCatalogNotFoundError"),
}

def __getattr__(name: str):
    target = _ATTR_MAP.get(name)
    if target is None:
        raise AttributeError(name)
    module_path, attr = target
    module = importlib.import_module(module_path)
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(__all__))
