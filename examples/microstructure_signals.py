"""Example pipeline for microstructure signals."""

from __future__ import annotations

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.transforms import (
    order_book_imbalance_node,
    logistic_order_book_imbalance_node,
    micro_price_node,
)


def build_example_nodes():
    """Create nodes for imbalance, logistic weight, and micro-price."""

    bid_volume = SourceNode(interval="1s", period=1, config={"id": "bid_volume"})
    ask_volume = SourceNode(interval="1s", period=1, config={"id": "ask_volume"})
    best_bid = SourceNode(interval="1s", period=1, config={"id": "best_bid"})
    best_ask = SourceNode(interval="1s", period=1, config={"id": "best_ask"})

    imbalance = order_book_imbalance_node(bid_volume, ask_volume)
    logistic_weight = logistic_order_book_imbalance_node(
        bid_volume,
        ask_volume,
        slope=4.0,
        clamp=0.8,
    )
    micro_price = micro_price_node(
        best_bid,
        best_ask,
        weight_node=logistic_weight,
    )

    return {
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "imbalance": imbalance,
        "logistic_weight": logistic_weight,
        "micro_price": micro_price,
    }


def compute_example_snapshot():
    """Compute the nodes using a single synthetic snapshot."""

    nodes = build_example_nodes()
    bid_volume = nodes["bid_volume"]
    ask_volume = nodes["ask_volume"]
    best_bid = nodes["best_bid"]
    best_ask = nodes["best_ask"]
    imbalance = nodes["imbalance"]
    logistic_weight = nodes["logistic_weight"]
    micro_price = nodes["micro_price"]

    cache = CacheView(
        {
            bid_volume.node_id: {1: [(0, 120.0)]},
            ask_volume.node_id: {1: [(0, 80.0)]},
            best_bid.node_id: {1: [(0, 99.5)]},
            best_ask.node_id: {1: [(0, 100.0)]},
        }
    )

    imbalance_value = imbalance.compute_fn(cache)
    logistic_value = logistic_weight.compute_fn(cache)

    weight_cache = CacheView(
        {
            bid_volume.node_id: {1: [(0, 120.0)]},
            ask_volume.node_id: {1: [(0, 80.0)]},
            best_bid.node_id: {1: [(0, 99.5)]},
            best_ask.node_id: {1: [(0, 100.0)]},
            logistic_weight.node_id: {1: [(0, logistic_value)]},
        }
    )
    micro_price_value = micro_price.compute_fn(weight_cache)

    return {
        "imbalance": imbalance_value,
        "logistic_weight": logistic_value,
        "micro_price": micro_price_value,
    }


def main() -> None:
    """Print example outputs for quick verification."""

    snapshot = compute_example_snapshot()
    for key, value in snapshot.items():
        print(f"{key}: {value:.6f}")


if __name__ == "__main__":
    main()
