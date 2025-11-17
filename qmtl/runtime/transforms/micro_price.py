"""Micro-price transformation node."""

from __future__ import annotations

import math
from typing import Literal

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .order_book_imbalance import imbalance_to_weight


def _latest_price(view: CacheView, node: Node, interval: int | str) -> float | None:
    data = view[node][interval]
    sequence = getattr(data, "_data", data)
    if not sequence:
        return None
    price = sequence[-1][1]
    if not isinstance(price, (int, float)) or math.isnan(price):
        return None
    return float(price)


def _latest_scalar(view: CacheView, node: Node, interval: int | str) -> float | None:
    data = view[node][interval]
    sequence = getattr(data, "_data", data)
    if not sequence:
        return None
    value = sequence[-1][1]
    if not isinstance(value, (int, float)) or math.isnan(value):
        return None
    return float(value)


def micro_price(
    bid_price: float,
    ask_price: float,
    weight: float,
) -> float:
    """Return micro-price from bid/ask quotes and a mixing weight."""

    return weight * ask_price + (1.0 - weight) * bid_price


def micro_price_from_imbalance(
    bid_price: float,
    ask_price: float,
    imbalance: float,
    *,
    mode: Literal["linear", "logistic"] = "linear",
    slope: float = 5.0,
    offset: float = 0.0,
    clamp: float | None = 0.9,
) -> float:
    weight = imbalance_to_weight(
        imbalance,
        mode=mode,
        slope=slope,
        offset=offset,
        clamp=clamp,
    )
    return micro_price(bid_price, ask_price, weight)


def micro_price_node(
    bid_price: Node,
    ask_price: Node,
    *,
    weight_node: Node | None = None,
    imbalance_node: Node | None = None,
    mode: Literal["linear", "logistic"] = "logistic",
    slope: float = 5.0,
    offset: float = 0.0,
    clamp: float | None = 0.9,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing micro-price from best quotes.

    Provide ``weight_node`` when pre-computed weights are available. Otherwise
    supply ``imbalance_node`` and specify how the imbalance should be mapped to a
    weight through ``mode`` (``"linear"`` or ``"logistic"``) and the optional
    logistic parameters ``slope``/``offset``/``clamp``.
    """

    if weight_node is None and imbalance_node is None:
        raise ValueError("Either weight_node or imbalance_node must be provided")

    if weight_node is not None and imbalance_node is not None:
        raise ValueError("Provide only one of weight_node or imbalance_node")

    interval = interval or bid_price.interval

    def compute(view: CacheView):
        bid = _latest_price(view, bid_price, interval)
        ask = _latest_price(view, ask_price, interval)
        if bid is None or ask is None:
            return None

        if weight_node is not None:
            weight = _latest_scalar(view, weight_node, interval)
            if weight is None:
                return None
        else:
            assert imbalance_node is not None
            imbalance = _latest_scalar(view, imbalance_node, interval)
            if imbalance is None:
                return None
            weight = imbalance_to_weight(
                imbalance,
                mode=mode,
                slope=slope,
                offset=offset,
                clamp=clamp,
            )

        weight = max(0.0, min(1.0, weight))
        return micro_price(bid, ask, weight)

    inputs = [bid_price, ask_price]
    if weight_node is not None:
        inputs.append(weight_node)
    else:
        assert imbalance_node is not None
        inputs.append(imbalance_node)

    return Node(
        input=inputs,
        compute_fn=compute,
        name=name or "micro_price",
        interval=interval,
    )


__all__ = [
    "micro_price",
    "micro_price_from_imbalance",
    "micro_price_node",
]
