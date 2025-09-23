"""Order and portfolio event schemas and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import importlib.resources as resources
from typing import Any, Dict

from .registry import SchemaRegistryClient

# Load JSON schema definitions from docs
_SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "docs" / "reference" / "schemas"


def _load_schema(name: str) -> str:
    """Load schema content from docs or bundled resources."""

    try:
        return (_SCHEMAS_DIR / name).read_text(encoding="utf-8")
    except FileNotFoundError:
        with resources.files("qmtl.foundation.schema.schemas").joinpath(name).open(
            "r", encoding="utf-8"
        ) as fh:
            return fh.read()

ORDER_PAYLOAD_SCHEMA = _load_schema("order_payload.schema.json")
ORDER_ACK_SCHEMA = _load_schema("order_ack.schema.json")
EXECUTION_FILL_EVENT_SCHEMA = _load_schema("execution_fill_event.schema.json")
PORTFOLIO_SNAPSHOT_SCHEMA = _load_schema("portfolio_snapshot.schema.json")


@dataclass
class OrderPayload:
    world_id: str
    strategy_id: str
    correlation_id: str
    symbol: str
    side: str
    type: str
    quantity: float
    time_in_force: str
    timestamp: int
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None
    reduce_only: bool | None = None
    position_side: str | None = None
    metadata: Dict[str, Any] | None = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        world_id: str,
        strategy_id: str,
        correlation_id: str,
        symbol: str,
        side: str,
        type: str,
        quantity: float,
        time_in_force: str,
        timestamp: int,
        limit_price: float | None = None,
        stop_price: float | None = None,
        client_order_id: str | None = None,
        reduce_only: bool | None = None,
        position_side: str | None = None,
        metadata: Dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        self.world_id = world_id
        self.strategy_id = strategy_id
        self.correlation_id = correlation_id
        self.symbol = symbol
        self.side = side
        self.type = type
        self.quantity = quantity
        self.time_in_force = time_in_force
        self.timestamp = timestamp
        self.limit_price = limit_price
        self.stop_price = stop_price
        self.client_order_id = client_order_id
        self.reduce_only = reduce_only
        self.position_side = position_side
        self.metadata = metadata
        self.extra = extra


@dataclass
class OrderAck:
    order_id: str
    status: str
    broker: str
    client_order_id: str | None = None
    reason: str | None = None
    raw: Dict[str, Any] | None = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        order_id: str,
        status: str,
        broker: str,
        client_order_id: str | None = None,
        reason: str | None = None,
        raw: Dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        self.order_id = order_id
        self.status = status
        self.broker = broker
        self.client_order_id = client_order_id
        self.reason = reason
        self.raw = raw
        self.extra = extra


@dataclass
class ExecutionFillEvent:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float
    slippage: float
    market_impact: float
    tif: str
    fill_time: int
    status: str
    seq: int
    etag: str
    client_order_id: str | None = None
    correlation_id: str | None = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        commission: float,
        slippage: float,
        market_impact: float,
        tif: str,
        fill_time: int,
        status: str,
        seq: int,
        etag: str,
        client_order_id: str | None = None,
        correlation_id: str | None = None,
        **extra: Any,
    ) -> None:
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.commission = commission
        self.slippage = slippage
        self.market_impact = market_impact
        self.tif = tif
        self.fill_time = fill_time
        self.status = status
        self.seq = seq
        self.etag = etag
        self.client_order_id = client_order_id
        self.correlation_id = correlation_id
        self.extra = extra


@dataclass
class PortfolioSnapshot:
    world_id: str
    as_of: int
    cash: float
    positions: Dict[str, Dict[str, float]]
    strategy_id: str | None = None
    metrics: Dict[str, float] | None = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        world_id: str,
        as_of: int,
        cash: float,
        positions: Dict[str, Dict[str, float]],
        strategy_id: str | None = None,
        metrics: Dict[str, float] | None = None,
        **extra: Any,
    ) -> None:
        self.world_id = world_id
        self.as_of = as_of
        self.cash = cash
        self.positions = positions
        self.strategy_id = strategy_id
        self.metrics = metrics
        self.extra = extra


def register_order_schemas(registry: SchemaRegistryClient) -> None:
    """Register order-related schemas in ``registry``."""

    registry.register("OrderPayload", ORDER_PAYLOAD_SCHEMA)
    registry.register("OrderAck", ORDER_ACK_SCHEMA)
    registry.register("ExecutionFillEvent", EXECUTION_FILL_EVENT_SCHEMA)
    registry.register("PortfolioSnapshot", PORTFOLIO_SNAPSHOT_SCHEMA)


__all__ = [
    "OrderPayload",
    "OrderAck",
    "ExecutionFillEvent",
    "PortfolioSnapshot",
    "register_order_schemas",
    "ORDER_PAYLOAD_SCHEMA",
    "ORDER_ACK_SCHEMA",
    "EXECUTION_FILL_EVENT_SCHEMA",
    "PORTFOLIO_SNAPSHOT_SCHEMA",
]
