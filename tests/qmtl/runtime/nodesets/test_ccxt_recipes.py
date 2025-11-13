from __future__ import annotations

import pytest

from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.brokerage_client import FakeBrokerageClient
from qmtl.runtime.nodesets.recipes import (
    make_ccxt_futures_nodeset,
    make_ccxt_spot_nodeset,
)


def _make_signal() -> Node:
    price = StreamInput(interval="60s", period=1)
    return Node(input=price, compute_fn=lambda view: {})


def _view_for(node: Node, payload: dict) -> CacheView:
    return CacheView({node.node_id: {node.interval: [(0, payload)]}})


def test_ccxt_spot_execution_and_publish(monkeypatch):
    signal = _make_signal()
    published: list[dict] = []

    def _fake_post(self, order):
        published.append(order)
        return {"status": "ok", "order": order}

    monkeypatch.setattr(FakeBrokerageClient, "post_order", _fake_post)

    nodeset = make_ccxt_spot_nodeset(
        signal,
        "world",
        exchange_id="binance",
        time_in_force="IOC",
        reduce_only=True,
    )

    _, sizing, execution_node, publish_node, *_ = nodeset.nodes

    base_order = {"symbol": "BTC/USDT", "type": "limit", "quantity": 1}
    exec_order = execution_node.compute_fn(_view_for(sizing, base_order))

    assert exec_order["time_in_force"] == "IOC"
    assert exec_order["reduce_only"] is True

    publish_node.compute_fn(_view_for(execution_node, exec_order))

    assert published == [exec_order]


def test_ccxt_futures_execution_and_publish(monkeypatch):
    signal = _make_signal()
    published: list[dict] = []

    def _fake_post(self, order):
        published.append(order)
        return {"status": "ok", "order": order}

    monkeypatch.setattr(FakeBrokerageClient, "post_order", _fake_post)

    nodeset = make_ccxt_futures_nodeset(
        signal,
        "world",
        leverage=5,
        reduce_only=True,
    )

    _, sizing, execution_node, publish_node, *_ = nodeset.nodes

    base_order = {"symbol": "BTC/USDT", "type": "limit", "quantity": 2}
    exec_order = execution_node.compute_fn(_view_for(sizing, base_order))

    assert exec_order["time_in_force"] == "GTC"
    assert exec_order["reduce_only"] is True
    assert exec_order["leverage"] == 5

    publish_node.compute_fn(_view_for(execution_node, exec_order))

    assert published[-1]["leverage"] == 5


def test_ccxt_futures_sandbox_requires_credentials():
    signal = _make_signal()

    with pytest.raises(RuntimeError):
        make_ccxt_futures_nodeset(signal, "world", sandbox=True)
