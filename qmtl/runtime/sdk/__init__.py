"""QMTL strategy SDK."""

from __future__ import annotations

import importlib
from typing import Any, Callable, Mapping

__all__ = [
    "Node",
    "SourceNode",
    "ProcessingNode",
    "StreamInput",
    "TagQueryNode",
    "NodeCache",
    "MatchMode",
    "NodeCacheArrow",
    "BackfillState",
    "CacheView",
    "CacheWindow",
    "CacheFrame",
    "Strategy",
    "buy_signal",
    "Runner",
    "TagQueryManager",
    "WebSocketClient",
    "HistoryProvider",
    "HistoryBackend",
    "DataFetcher",
    "EventRecorder",
    "StreamLike",
    "NodeLike",
    "AutoBackfillRequest",
    "AugmentedHistoryProvider",
    "AutoBackfillStrategy",
    "QuestDBBackend",
    "QuestDBHistoryProvider",
    "QuestDBLoader",
    "QuestDBRecorder",
    "BackfillEngine",
    "metrics",
    "TradeExecutionService",
    "EventRecorderService",
    "BrokerageClient",
    "HttpBrokerageClient",
    "FakeBrokerageClient",
    "CcxtBrokerageClient",
    "FuturesCcxtBrokerageClient",
    "OCOOrder",
    "LiveDataFeed",
    "WebSocketFeed",
    "FakeLiveDataFeed",
    "Portfolio",
    "Position",
    "order_value",
    "order_percent",
    "order_target_percent",
    "parse_interval",
    "parse_period",
    "validate_tag",
    "validate_name",
    "CcxtExchange",
    "normalize_exchange_id",
    "ensure_ccxt_exchange",
    "FetcherBackfillStrategy",
    "LiveReplayBackfillStrategy",
    "QMTLValidationError",
    "NodeValidationError",
    "InvalidParameterError",
    "InvalidTagError",
    "InvalidIntervalError",
    "InvalidPeriodError",
    "InvalidNameError",
    "_cli",
    "SeamlessBuilder",
    "SeamlessAssembly",
    "SeamlessPresetRegistry",
    "hydrate_builder",
    "build_seamless_assembly",
]

_ATTR_MAP: Mapping[str, tuple[str, str | None]] = {
    # Nodes and cache
    "Node": ("qmtl.runtime.sdk.node", "Node"),
    "SourceNode": ("qmtl.runtime.sdk.node", "SourceNode"),
    "ProcessingNode": ("qmtl.runtime.sdk.node", "ProcessingNode"),
    "StreamInput": ("qmtl.runtime.sdk.node", "StreamInput"),
    "TagQueryNode": ("qmtl.runtime.sdk.node", "TagQueryNode"),
    "NodeCache": ("qmtl.runtime.sdk.node", "NodeCache"),
    "MatchMode": ("qmtl.runtime.sdk.node", "MatchMode"),
    "NodeCacheArrow": ("qmtl.runtime.sdk.arrow_cache", "NodeCacheArrow"),
    "BackfillState": ("qmtl.runtime.sdk.backfill_state", "BackfillState"),
    "CacheView": ("qmtl.runtime.sdk.cache_view", "CacheView"),
    "CacheWindow": ("qmtl.runtime.sdk.cache_view", "CacheWindow"),
    "CacheFrame": ("qmtl.runtime.sdk.cache_view_tools", "CacheFrame"),
    "StreamLike": ("qmtl.runtime.sdk.protocols", "StreamLike"),
    "NodeLike": ("qmtl.runtime.sdk.protocols", "NodeLike"),
    # Strategies
    "Strategy": ("qmtl.runtime.sdk.strategy", "Strategy"),
    "buy_signal": ("qmtl.runtime.sdk.strategy", "buy_signal"),
    "Runner": ("qmtl.runtime.sdk.runner", "Runner"),
    "TagQueryManager": ("qmtl.runtime.sdk.tagquery_manager", "TagQueryManager"),
    "_cli": ("qmtl.runtime.sdk.cli", "main"),
    "WebSocketClient": ("qmtl.runtime.sdk.ws_client", "WebSocketClient"),
    # Data I/O
    "AutoBackfillRequest": ("qmtl.runtime.sdk.data_io", "AutoBackfillRequest"),
    "DataFetcher": ("qmtl.runtime.sdk.data_io", "DataFetcher"),
    "EventRecorder": ("qmtl.runtime.sdk.data_io", "EventRecorder"),
    "HistoryBackend": ("qmtl.runtime.sdk.data_io", "HistoryBackend"),
    "HistoryProvider": ("qmtl.runtime.sdk.data_io", "HistoryProvider"),
    "AugmentedHistoryProvider": (
        "qmtl.runtime.sdk.history_provider_facade",
        "AugmentedHistoryProvider",
    ),
    # IO providers
    "QuestDBBackend": ("qmtl.runtime.io.historyprovider", "QuestDBBackend"),
    "QuestDBHistoryProvider": ("qmtl.runtime.io.historyprovider", "QuestDBHistoryProvider"),
    "QuestDBLoader": ("qmtl.runtime.io.historyprovider", "QuestDBLoader"),
    "QuestDBRecorder": ("qmtl.runtime.io.eventrecorder", "QuestDBRecorder"),
    "BackfillEngine": ("qmtl.runtime.sdk.backfill_engine", "BackfillEngine"),
    # Helpers and validation
    "parse_interval": ("qmtl.runtime.sdk.util", "parse_interval"),
    "parse_period": ("qmtl.runtime.sdk.util", "parse_period"),
    "validate_tag": ("qmtl.runtime.sdk.util", "validate_tag"),
    "validate_name": ("qmtl.runtime.sdk.util", "validate_name"),
    # Exceptions
    "QMTLValidationError": ("qmtl.runtime.sdk.exceptions", "QMTLValidationError"),
    "NodeValidationError": ("qmtl.runtime.sdk.exceptions", "NodeValidationError"),
    "InvalidParameterError": ("qmtl.runtime.sdk.exceptions", "InvalidParameterError"),
    "InvalidTagError": ("qmtl.runtime.sdk.exceptions", "InvalidTagError"),
    "InvalidIntervalError": ("qmtl.runtime.sdk.exceptions", "InvalidIntervalError"),
    "InvalidPeriodError": ("qmtl.runtime.sdk.exceptions", "InvalidPeriodError"),
    "InvalidNameError": ("qmtl.runtime.sdk.exceptions", "InvalidNameError"),
    # Metrics and services
    "metrics": ("qmtl.runtime.sdk.metrics", None),  # module passthrough
    "TradeExecutionService": ("qmtl.runtime.sdk.trade_execution_service", "TradeExecutionService"),
    "EventRecorderService": ("qmtl.runtime.sdk.event_service", "EventRecorderService"),
    # Brokerage
    "BrokerageClient": ("qmtl.runtime.sdk.brokerage_client", "BrokerageClient"),
    "HttpBrokerageClient": ("qmtl.runtime.sdk.brokerage_client", "HttpBrokerageClient"),
    "FakeBrokerageClient": ("qmtl.runtime.sdk.brokerage_client", "FakeBrokerageClient"),
    "CcxtBrokerageClient": ("qmtl.runtime.sdk.brokerage_client", "CcxtBrokerageClient"),
    "FuturesCcxtBrokerageClient": ("qmtl.runtime.sdk.brokerage_client", "FuturesCcxtBrokerageClient"),
    # Orders and live data
    "OCOOrder": ("qmtl.runtime.sdk.oco", "OCOOrder"),
    "LiveDataFeed": ("qmtl.runtime.sdk.live_data_feed", "LiveDataFeed"),
    "WebSocketFeed": ("qmtl.runtime.sdk.live_data_feed", "WebSocketFeed"),
    "FakeLiveDataFeed": ("qmtl.runtime.sdk.live_data_feed", "FakeLiveDataFeed"),
    # Portfolio helpers
    "Portfolio": ("qmtl.runtime.sdk.portfolio", "Portfolio"),
    "Position": ("qmtl.runtime.sdk.portfolio", "Position"),
    "order_value": ("qmtl.runtime.sdk.portfolio", "order_value"),
    "order_percent": ("qmtl.runtime.sdk.portfolio", "order_percent"),
    "order_target_percent": ("qmtl.runtime.sdk.portfolio", "order_target_percent"),
    # Exchange helpers
    "CcxtExchange": ("qmtl.runtime.sdk.exchanges", "CcxtExchange"),
    "normalize_exchange_id": ("qmtl.runtime.sdk.exchanges", "normalize_exchange_id"),
    "ensure_ccxt_exchange": ("qmtl.runtime.sdk.exchanges", "ensure_ccxt_exchange"),
    # Seamless
    "FetcherBackfillStrategy": ("qmtl.runtime.sdk.auto_backfill", "FetcherBackfillStrategy"),
    "LiveReplayBackfillStrategy": ("qmtl.runtime.sdk.auto_backfill", "LiveReplayBackfillStrategy"),
    "AutoBackfillStrategy": ("qmtl.runtime.sdk.auto_backfill", "AutoBackfillStrategy"),
    "SeamlessBuilder": ("qmtl.runtime.sdk.seamless", "SeamlessBuilder"),
    "SeamlessAssembly": ("qmtl.runtime.sdk.seamless", "SeamlessAssembly"),
    "SeamlessPresetRegistry": ("qmtl.runtime.sdk.seamless", "SeamlessPresetRegistry"),
    "hydrate_builder": ("qmtl.runtime.sdk.seamless", "hydrate_builder"),
    "build_seamless_assembly": ("qmtl.runtime.sdk.seamless", "build_assembly"),
}


def __getattr__(name: str) -> Any:
    target = _ATTR_MAP.get(name)
    if target is None:
        raise AttributeError(name)
    module_path, attr = target
    module = importlib.import_module(module_path)
    value = module if attr is None else getattr(module, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__))
