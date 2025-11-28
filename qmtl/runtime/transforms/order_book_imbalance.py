"""Order book imbalance transformation nodes and helpers."""

from __future__ import annotations

import math
from typing import Callable

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def _latest(view: CacheView, node: Node, interval: int | str) -> float | None:
    """Return the most recent scalar payload for *node* at *interval*."""

    data = view[node][interval]
    if not data:
        return None
    value = data[-1][1]
    if not isinstance(value, (int, float)) or math.isnan(value):
        return None
    return float(value)


def order_book_imbalance_node(
    bid_volume: Node,
    ask_volume: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing order book imbalance.

    The imbalance is ``(bid_volume - ask_volume) / (bid_volume + ask_volume)``.
    """

    interval = interval or bid_volume.interval
    if interval is None:
        raise ValueError("order_book_imbalance_node requires an interval")
    resolved_interval: int | str = interval

    def compute(view: CacheView):
        b = _latest(view, bid_volume, resolved_interval)
        a = _latest(view, ask_volume, resolved_interval)
        if b is None or a is None:
            return None
        total = b + a
        if total == 0:
            return None
        return (b - a) / total

    return Node(
        input=[bid_volume, ask_volume],
        compute_fn=compute,
        name=name or "order_book_imbalance",
        interval=resolved_interval,
    )


def order_book_imbalance(bid_volume: float, ask_volume: float) -> float:
    """Return order book imbalance from raw volumes."""
    total = bid_volume + ask_volume
    if total == 0:
        return 0.0
    return (bid_volume - ask_volume) / total


def _sigmoid(z: float) -> float:
    """Numerically stable logistic function."""

    if z >= 0:
        exp_neg = math.exp(-z)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(z)
    return exp_pos / (1.0 + exp_pos)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def imbalance_to_weight(
    imbalance: float,
    *,
    mode: str = "linear",
    slope: float = 5.0,
    offset: float = 0.0,
    clamp: float | None = None,
    floor: float = 0.0,
    ceiling: float = 1.0,
) -> float:
    """Convert an imbalance in ``[-1, 1]`` into a mixing weight ``[0, 1]``.

    Parameters
    ----------
    imbalance:
        Raw imbalance value.
    mode:
        ``"linear"`` (default) maps via ``(1 + imbalance) / 2`` while
        ``"logistic"`` applies a sigmoid with the provided ``slope`` and
        ``offset``.
    clamp:
        Optional absolute cap applied to the imbalance before the mapping is
        evaluated. This helps avoid excessive saturation from thin-book noise.
    floor, ceiling:
        Clamp the resulting weight into the inclusive range ``[floor, ceiling]``.
    """

    if clamp is not None:
        clamp = max(0.0, float(clamp))
        imbalance = _clamp(imbalance, -clamp, clamp)

    if mode == "linear":
        weight = 0.5 * (1.0 + imbalance)
    elif mode == "logistic":
        slope = float(slope)
        if slope == 0:
            weight = 0.5
        else:
            z = slope * (imbalance - offset)
            weight = _sigmoid(z)
    else:
        raise ValueError(f"Unsupported imbalance weight mode: {mode!r}")

    return _clamp(weight, floor, ceiling)


def logistic_order_book_weight(
    bid_volume: float,
    ask_volume: float,
    *,
    slope: float = 5.0,
    offset: float = 0.0,
    clamp: float | None = 0.9,
    floor: float = 0.0,
    ceiling: float = 1.0,
) -> float:
    """Return a logistic weight derived from raw order-book volumes."""

    imbalance = order_book_imbalance(bid_volume, ask_volume)
    return imbalance_to_weight(
        imbalance,
        mode="logistic",
        slope=slope,
        offset=offset,
        clamp=clamp,
        floor=floor,
        ceiling=ceiling,
    )


def _imbalance_node_compute(
    bid_volume: Node,
    ask_volume: Node,
    *,
    interval: int | str,
    mapper: Callable[[float], float | None],
) -> Callable[[CacheView], float | None]:
    def compute(view: CacheView):
        b = _latest(view, bid_volume, interval)
        a = _latest(view, ask_volume, interval)
        if b is None or a is None:
            return None
        total = b + a
        if total == 0:
            return None
        return mapper((b - a) / total)

    return compute


def logistic_order_book_imbalance_node(
    bid_volume: Node,
    ask_volume: Node,
    *,
    slope: float = 5.0,
    offset: float = 0.0,
    clamp: float | None = 0.9,
    floor: float = 0.0,
    ceiling: float = 1.0,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing a logistic weight from order-book imbalance."""

    interval = interval or bid_volume.interval
    if interval is None:
        raise ValueError("logistic_order_book_imbalance_node requires an interval")
    resolved_interval: int | str = interval

    def mapper(imbalance: float) -> float:
        return imbalance_to_weight(
            imbalance,
            mode="logistic",
            slope=slope,
            offset=offset,
            clamp=clamp,
            floor=floor,
            ceiling=ceiling,
        )

    return Node(
        input=[bid_volume, ask_volume],
        compute_fn=_imbalance_node_compute(
            bid_volume,
            ask_volume,
            interval=resolved_interval,
            mapper=mapper,
        ),
        name=name or "logistic_order_book_weight",
        interval=resolved_interval,
    )


__all__ = [
    "order_book_imbalance_node",
    "order_book_imbalance",
    "logistic_order_book_weight",
    "logistic_order_book_imbalance_node",
    "imbalance_to_weight",
]
