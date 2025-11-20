"""QMTL strategy SDK."""

from .node import (
    Node,
    SourceNode,
    ProcessingNode,
    StreamInput,
    TagQueryNode,
    NodeCache,
    MatchMode,
)
from .arrow_cache import NodeCacheArrow
from .backfill_state import BackfillState
from .cache_view import CacheView
from .cache_view_tools import CacheFrame
from .auto_backfill import (
    AutoBackfillStrategy,
    FetcherBackfillStrategy,
    LiveReplayBackfillStrategy,
)
from .strategy import Strategy, buy_signal
from .runner import Runner
from .tagquery_manager import TagQueryManager
from .cli import main as _cli
from .ws_client import WebSocketClient
from . import arrow_cache
from qmtl.runtime.sdk.data_io import (
    AutoBackfillRequest,
    DataFetcher,
    EventRecorder,
    HistoryBackend,
    HistoryProvider,
)
from qmtl.runtime.sdk.history_provider_facade import AugmentedHistoryProvider
from qmtl.runtime.io import (
    QuestDBBackend,
    QuestDBHistoryProvider,
    QuestDBLoader,
    QuestDBRecorder,
)
from .backfill_engine import BackfillEngine
from .util import parse_interval, parse_period, validate_tag, validate_name
from .exceptions import (
    QMTLValidationError,
    NodeValidationError,
    InvalidParameterError,
    InvalidTagError,
    InvalidIntervalError,
    InvalidPeriodError,
    InvalidNameError,
)
from . import metrics
from .trade_execution_service import TradeExecutionService
from .event_service import EventRecorderService
from .brokerage_client import (
    BrokerageClient,
    HttpBrokerageClient,
    FakeBrokerageClient,
    CcxtBrokerageClient,
    FuturesCcxtBrokerageClient,
)
from .oco import OCOOrder
from .live_data_feed import LiveDataFeed, WebSocketFeed, FakeLiveDataFeed
from .portfolio import (
    Portfolio,
    Position,
    order_percent,
    order_target_percent,
    order_value,
)
from .exchanges import CcxtExchange, normalize_exchange_id, ensure_ccxt_exchange
from .seamless import (
    SeamlessAssembly,
    SeamlessBuilder,
    SeamlessPresetRegistry,
    hydrate_builder,
    build_assembly as build_seamless_assembly,
)

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
