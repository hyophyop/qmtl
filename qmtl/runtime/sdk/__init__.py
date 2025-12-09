"""QMTL Strategy SDK.

QMTL v2.0 provides a simplified API for strategy development.

Primary API (what users need):
  Runner      Submit and run strategies
  Strategy    Base class for strategy definition
  Mode        Execution mode (backtest | paper | live)

Example:
    from qmtl.runtime.sdk import Runner, Strategy, Mode

    class MyStrategy(Strategy):
        def setup(self):
            ...

    result = Runner.submit(MyStrategy)
    print(result.status)

For advanced usage, import from submodules:
    from qmtl.runtime.sdk.node import Node, StreamInput, ProcessingNode
    from qmtl.runtime.sdk.presets import PolicyPreset
"""

from __future__ import annotations

import importlib
from typing import Any, Mapping

# =============================================================================
# PUBLIC API - What users need to know
# =============================================================================

__all__ = [
    # Core API (3 essentials)
    "Runner",
    "Strategy",
    "Mode",
    # Result types
    "SubmitResult",
    "StrategyMetrics",
]

# =============================================================================
# LAZY LOADING
# =============================================================================

_PUBLIC_API: Mapping[str, tuple[str, str]] = {
    # Core API
    "Runner": ("qmtl.runtime.sdk.runner", "Runner"),
    "Strategy": ("qmtl.runtime.sdk.strategy", "Strategy"),
    "Mode": ("qmtl.runtime.sdk.mode", "Mode"),
    # Result types
    "SubmitResult": ("qmtl.runtime.sdk.submit", "SubmitResult"),
    "StrategyMetrics": ("qmtl.runtime.sdk.submit", "StrategyMetrics"),
}

# Extended API - available but not advertised in __all__
# Users can import these directly from submodules
_EXTENDED_API: Mapping[str, tuple[str, str | None]] = {
    # Mode utilities
    "mode_to_execution_domain": ("qmtl.runtime.sdk.mode", "mode_to_execution_domain"),
    "execution_domain_to_mode": ("qmtl.runtime.sdk.mode", "execution_domain_to_mode"),
    "effective_mode_to_mode": ("qmtl.runtime.sdk.mode", "effective_mode_to_mode"),
    "is_orders_enabled": ("qmtl.runtime.sdk.mode", "is_orders_enabled"),
    "is_real_time_data": ("qmtl.runtime.sdk.mode", "is_real_time_data"),
    "normalize_mode": ("qmtl.runtime.sdk.mode", "normalize_mode"),
    # Policy presets
    "PolicyPreset": ("qmtl.runtime.sdk.presets", "PolicyPreset"),
    "get_preset": ("qmtl.runtime.sdk.presets", "get_preset"),
    "list_presets": ("qmtl.runtime.sdk.presets", "list_presets"),
    # Validation pipeline
    "ValidationPipeline": ("qmtl.runtime.sdk.validation_pipeline", "ValidationPipeline"),
    "ValidationResult": ("qmtl.runtime.sdk.validation_pipeline", "ValidationResult"),
    "ValidationStatus": ("qmtl.runtime.sdk.validation_pipeline", "ValidationStatus"),
    "validate_strategy": ("qmtl.runtime.sdk.validation_pipeline", "validate_strategy"),
    "validate_strategy_sync": ("qmtl.runtime.sdk.validation_pipeline", "validate_strategy_sync"),
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
    # Other utilities
    "buy_signal": ("qmtl.runtime.sdk.strategy", "buy_signal"),
    "TagQueryManager": ("qmtl.runtime.sdk.tagquery_manager", "TagQueryManager"),
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
    "MaterializeSeamlessJob": ("qmtl.runtime.sdk.materialize_job", "MaterializeSeamlessJob"),
    "MaterializeReport": ("qmtl.runtime.sdk.materialize_job", "MaterializeReport"),
    # Evaluation run helpers
    "EvaluationRunStatus": ("qmtl.runtime.sdk.evaluation_runs", "EvaluationRunStatus"),
}

_ALL_API = {**_PUBLIC_API, **_EXTENDED_API}


def __getattr__(name: str) -> Any:
    target = _ALL_API.get(name)
    if target is None:
        raise AttributeError(name)
    module_path, attr = target
    module = importlib.import_module(module_path)
    value = module if attr is None else getattr(module, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    # Only show public API in dir()
    return sorted(set(__all__))
