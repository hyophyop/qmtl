from __future__ import annotations

"""Typed order payload contracts shared across execution nodes."""

from typing import Literal, Mapping, MutableMapping, TypedDict, cast
from typing import NotRequired
from typing_extensions import Required

from qmtl.runtime.brokerage import OrderType, TimeInForce


class OrderIntent(TypedDict, total=False):
    """Upstream order intent before sizing/validation."""

    symbol: str
    price: NotRequired[float]
    side: str
    action: NotRequired[str]
    order_type: NotRequired[OrderType | str]
    tif: NotRequired[TimeInForce | str]
    time_in_force: NotRequired[TimeInForce | str]
    limit_price: NotRequired[float]
    stop_price: NotRequired[float]
    value: NotRequired[float]
    percent: NotRequired[float]
    target_percent: NotRequired[float]
    route: NotRequired[str]
    client_order_id: NotRequired[str]
    reduce_only: NotRequired[bool]
    position_side: NotRequired[str]
    leverage: NotRequired[float]
    metadata: NotRequired[Mapping[str, object]]


class SizedOrder(TypedDict, total=False):
    """Order intent with resolved quantity."""

    symbol: str
    price: Required[float]
    quantity: Required[float]
    side: NotRequired[str]
    order_type: NotRequired[OrderType | str]
    tif: NotRequired[TimeInForce | str]
    time_in_force: NotRequired[TimeInForce | str]
    limit_price: NotRequired[float]
    stop_price: NotRequired[float]
    route: NotRequired[str]
    client_order_id: NotRequired[str]
    reduce_only: NotRequired[bool]
    position_side: NotRequired[str]
    leverage: NotRequired[float]
    metadata: NotRequired[Mapping[str, object]]


class OrderRejection(TypedDict):
    """Standard rejection payload produced by gating nodes."""

    rejected: Literal[True]
    reason: str


class RiskRejection(OrderRejection, total=False):
    """Risk-specific rejection with violation details."""

    violation: NotRequired[str]


class ExecutionFillPayload(TypedDict):
    """Execution fill emitted by simulation or live adapters."""

    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    requested_price: float
    fill_price: float
    fill_time: int
    commission: float
    slippage: float
    market_impact: float


class FillPayload(TypedDict, total=False):
    """Normalized fill payload consumed by PortfolioNode."""

    symbol: str
    quantity: float
    fill_price: float
    price: NotRequired[float]
    commission: NotRequired[float]
    timestamp: NotRequired[int]
    order_id: NotRequired[str]
    client_order_id: NotRequired[str]


class GatewayOrderPayload(TypedDict, total=False):
    """Order payload enriched for Gateway/commit-log boundaries."""

    symbol: Required[str]
    price: Required[float]
    quantity: Required[float]
    side: NotRequired[str]
    order_type: NotRequired[OrderType | str]
    tif: NotRequired[TimeInForce | str]
    time_in_force: NotRequired[str | TimeInForce]
    limit_price: NotRequired[float]
    stop_price: NotRequired[float]
    route: NotRequired[str]
    client_order_id: NotRequired[str]
    reduce_only: NotRequired[bool]
    position_side: NotRequired[str]
    leverage: NotRequired[float]
    metadata: NotRequired[Mapping[str, object]]
    world_id: NotRequired[str]
    strategy_id: NotRequired[str]
    correlation_id: NotRequired[str]
    type: NotRequired[str | OrderType]


OrderPayload = Mapping[str, object]
MutableOrderPayload = MutableMapping[str, object]


def as_order_dict(order: OrderPayload | MutableOrderPayload | None) -> dict[str, object] | None:
    """Return a shallow dict copy when *order* is mapping-like."""

    if not isinstance(order, Mapping):
        return None
    try:
        return dict(order)
    except Exception:
        return None


def normalize_order_intent(order: OrderPayload | MutableOrderPayload | None) -> OrderIntent | SizedOrder | None:
    """Normalize loose order-like payloads into a predictable dict."""

    normalized = as_order_dict(order)
    if normalized is None:
        return None

    if not _has_symbol(normalized):
        return None

    _apply_side_aliases(normalized)
    _apply_type_aliases(normalized)
    _apply_time_in_force_alias(normalized)
    _apply_quantity_alias(normalized)
    _infer_limit_price(normalized)

    return cast(OrderIntent | SizedOrder, normalized)


def _has_symbol(order: dict[str, object]) -> bool:
    symbol = order.get("symbol")
    return isinstance(symbol, str) and bool(symbol)


def _apply_side_aliases(order: dict[str, object]) -> None:
    if "side" in order:
        return
    action = order.get("action")
    if isinstance(action, str):
        order["side"] = action


def _apply_type_aliases(order: dict[str, object]) -> None:
    if "type" not in order and "order_type" in order:
        order["type"] = order.get("order_type")


def _apply_time_in_force_alias(order: dict[str, object]) -> None:
    if "time_in_force" not in order and "tif" in order:
        order["time_in_force"] = order.get("tif")


def _apply_quantity_alias(order: dict[str, object]) -> None:
    if "quantity" not in order and "size" in order:
        order["quantity"] = order["size"]


def _infer_limit_price(order: dict[str, object]) -> None:
    if "price" not in order or "limit_price" in order:
        return
    typ = order.get("type")
    if typ in {OrderType.LIMIT, OrderType.STOP_LIMIT, "limit", "stop_limit"}:
        order["limit_price"] = order.get("price")


def prepare_gateway_payload(
    order: GatewayOrderPayload | OrderPayload | MutableOrderPayload,
    *,
    world_id: str | None = None,
    strategy_id: str | None = None,
    correlation_id: str | None = None,
    include_metadata: bool = False,
) -> GatewayOrderPayload:
    """Return a Gateway/commit-log friendly order payload."""

    payload: dict[str, object] = dict(order)
    if include_metadata:
        _attach_metadata(payload, world_id=world_id, strategy_id=strategy_id, correlation_id=correlation_id)
    _apply_type_aliases(payload)
    _apply_time_in_force_alias(payload)
    return cast(GatewayOrderPayload, payload)


def _attach_metadata(
    payload: dict[str, object],
    *,
    world_id: str | None,
    strategy_id: str | None,
    correlation_id: str | None,
) -> None:
    if world_id and "world_id" not in payload:
        payload["world_id"] = world_id
    if strategy_id and "strategy_id" not in payload:
        payload["strategy_id"] = strategy_id
    if correlation_id and "correlation_id" not in payload:
        payload["correlation_id"] = correlation_id


__all__ = [
    "ExecutionFillPayload",
    "FillPayload",
    "GatewayOrderPayload",
    "MutableOrderPayload",
    "OrderIntent",
    "OrderPayload",
    "OrderRejection",
    "RiskRejection",
    "SizedOrder",
    "as_order_dict",
    "normalize_order_intent",
    "prepare_gateway_payload",
]
