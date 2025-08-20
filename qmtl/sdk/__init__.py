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
from .strategy import Strategy
from .runner import Runner
from .tagquery_manager import TagQueryManager
from .cli import main as _cli
from .ws_client import WebSocketClient
from . import arrow_cache
from qmtl.sdk.data_io import (
    DataFetcher,
    HistoryProvider,
    EventRecorder,
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

# Brokerage models and execution engine
from .brokerage_models import (
    SymbolProperties, Currency, AccountType, ValidationResult,
    IBrokerageModel, IFeeModel, ISlippageModel, IBuyingPowerModel,
    ISettlementModel, IShortableProvider, IMarginInterestModel,
    DefaultSymbolPropertiesProvider, PercentageFeeModel, FixedFeeModel,
    PerShareFeeModel, VolumeShareSlippageModel, CashBuyingPowerModel,
    T2SettlementModel, DefaultShortableProvider, DefaultMarginInterestModel
)
from .brokerage_profiles import (
    InteractiveBrokersBrokerageModel, DefaultBrokerageModel, BrokerageFactory
)
from .execution_engine import (
    EnhancedExecutionEngine, Order, Portfolio, OrderStatus, TimeInForce
)
from .execution_modeling import (
    ExecutionModel, MarketData, OrderType, OrderSide, ExecutionFill,
    create_market_data_from_ohlcv
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
    "Strategy",
    "Runner",
    "TagQueryManager",
    "WebSocketClient",
    "HistoryProvider",
    "DataFetcher",
    "EventRecorder",
    "QuestDBLoader",
    "QuestDBRecorder",
    "BackfillEngine",
    "metrics",
    "TradeExecutionService",
    "parse_interval",
    "parse_period",
    "validate_tag",
    "validate_name",
    "QMTLValidationError",
    "NodeValidationError",
    "InvalidParameterError",
    "InvalidTagError",
    "InvalidIntervalError",
    "InvalidPeriodError",
    "InvalidNameError",
    "_cli",
    # Brokerage models
    "SymbolProperties",
    "Currency", 
    "AccountType",
    "ValidationResult",
    "IBrokerageModel",
    "IFeeModel",
    "ISlippageModel", 
    "IBuyingPowerModel",
    "ISettlementModel",
    "IShortableProvider",
    "IMarginInterestModel",
    "DefaultSymbolPropertiesProvider",
    "PercentageFeeModel",
    "FixedFeeModel",
    "PerShareFeeModel",
    "VolumeShareSlippageModel",
    "CashBuyingPowerModel",
    "T2SettlementModel",
    "DefaultShortableProvider",
    "DefaultMarginInterestModel",
    "InteractiveBrokersBrokerageModel",
    "DefaultBrokerageModel",
    "BrokerageFactory",
    "EnhancedExecutionEngine",
    "Order",
    "Portfolio",
    "OrderStatus",
    "TimeInForce",
    "ExecutionModel",
    "MarketData",
    "OrderType",
    "OrderSide",
    "ExecutionFill",
    "create_market_data_from_ohlcv",
]
