"""Microstructure feature transformation nodes.

Contains ask/bid gap depth-weighted sum, order-flow imbalance, spread z-score,
and hazard rate calculations.
"""

from __future__ import annotations

from typing import Iterable
import math

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


# Source: docs/alphadocs/ideas/gap-amplification-transition-theory.md
# Formula: sum_i (ask_i - bid_i) * (ask_vol_i + bid_vol_i) / sum_i (ask_vol_i + bid_vol_i)


def gap_depth_weighted_sum_node(
    bid_prices: Node,
    ask_prices: Node,
    bid_sizes: Node,
    ask_sizes: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return node computing depth-weighted ask/bid gap sum."""

    interval = interval or bid_prices.interval

    def _validate(seq: Iterable[float]) -> bool:
        try:
            return all(isinstance(v, (int, float)) and not math.isnan(v) for v in seq)
        except TypeError:
            return False

    def compute(view: CacheView):
        bids = view[bid_prices][interval]
        asks = view[ask_prices][interval]
        bid_vols = view[bid_sizes][interval]
        ask_vols = view[ask_sizes][interval]
        if not bids or not asks or not bid_vols or not ask_vols:
            return None
        b_list = bids[-1][1]
        a_list = asks[-1][1]
        bv_list = bid_vols[-1][1]
        av_list = ask_vols[-1][1]
        if not (
            _validate(b_list)
            and _validate(a_list)
            and _validate(bv_list)
            and _validate(av_list)
        ):
            return None
        n = min(len(b_list), len(a_list), len(bv_list), len(av_list))
        total_weight = 0.0
        weighted_sum = 0.0
        for i in range(n):
            weight = bv_list[i] + av_list[i]
            if weight <= 0:
                continue
            gap = a_list[i] - b_list[i]
            weighted_sum += gap * weight
            total_weight += weight
        if total_weight == 0:
            return None
        return weighted_sum / total_weight

    return Node(
        input=[bid_prices, ask_prices, bid_sizes, ask_sizes],
        compute_fn=compute,
        name=name or "gap_depth_weighted_sum",
        interval=interval,
    )


# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Formula: (buy_volume - sell_volume) / (buy_volume + sell_volume)


def order_flow_imbalance_node(
    buy_volume: Node,
    sell_volume: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return node computing order-flow imbalance."""
    from .utils import create_imbalance_node
    
    return create_imbalance_node(
        buy_volume,
        sell_volume,
        interval=interval,
        name=name or "order_flow_imbalance",
    )


# Source: docs/alphadocs/ideas/quote-compression-relaxation-cycle-transition-theory.md
# Formula: (spread_t - mean(spread)) / std(spread)


def spread_zscore_node(
    bid_price: Node,
    ask_price: Node,
    *,
    period: int,
    name: str | None = None,
) -> Node:
    """Return node computing z-score of bid-ask spread."""

    interval = bid_price.interval

    def compute(view: CacheView):
        bids_view = view[bid_price][interval]
        asks_view = view[ask_price][interval]
        bids = getattr(bids_view, "_data", bids_view)
        asks = getattr(asks_view, "_data", asks_view)
        if len(bids) < period or len(asks) < period:
            return None
        spreads = []
        for i in range(-period, 0):
            b = bids[i][1]
            a = asks[i][1]
            if not isinstance(b, (int, float)) or math.isnan(b):
                return None
            if not isinstance(a, (int, float)) or math.isnan(a):
                return None
            spreads.append(a - b)
        mean = sum(spreads) / period
        var = sum((s - mean) ** 2 for s in spreads) / period
        std = math.sqrt(var)
        if std == 0:
            return None
        return (spreads[-1] - mean) / std

    return Node(
        input=[bid_price, ask_price],
        compute_fn=compute,
        name=name or "spread_zscore",
        interval=interval,
        period=period,
    )


# Source: docs/alphadocs/ideas/micro-execution-probability-structure-collapse-theory.md
# Formula: event_count / population_at_risk


def hazard_node(
    event_count: Node,
    population: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return node computing discrete-time hazard rate."""

    interval = interval or event_count.interval

    def compute(view: CacheView):
        e_data = view[event_count][interval]
        p_data = view[population][interval]
        if not e_data or not p_data:
            return None
        e = e_data[-1][1]
        p = p_data[-1][1]
        if not isinstance(e, (int, float)) or math.isnan(e):
            return None
        if not isinstance(p, (int, float)) or math.isnan(p) or p <= 0:
            return None
        return e / p

    return Node(
        input=[event_count, population],
        compute_fn=compute,
        name=name or "hazard",
        interval=interval,
    )
