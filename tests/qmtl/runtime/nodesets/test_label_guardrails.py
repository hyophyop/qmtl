from __future__ import annotations

import logging

import pytest

from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.recipes import (
    make_intent_first_nodeset,
    make_labeling_triple_barrier_nodeset,
)
from qmtl.runtime.sdk import Node


def _make_label_nodeset(world_id: str = "world") -> tuple[Node, Node]:
    price = Node(name="price", interval=1, period=1, compute_fn=lambda view: None)
    entries = Node(name="entries", interval=1, period=1, compute_fn=lambda view: None)
    return price, entries


def test_live_order_path_blocks_label_output_signal() -> None:
    price, entries = _make_label_nodeset()
    label_nodeset = make_labeling_triple_barrier_nodeset(price, entries, "world")
    options = NodeSetOptions(mode="live", label_order_guard="block")

    with pytest.raises(ValueError, match="Label node output is connected"):
        make_intent_first_nodeset(
            label_nodeset.tail,
            "world",
            symbol="BTCUSDT",
            price_node=price,
            options=options,
        )


def test_live_order_path_warns_on_label_output_signal(caplog: pytest.LogCaptureFixture) -> None:
    price, entries = _make_label_nodeset("warn-world")
    label_nodeset = make_labeling_triple_barrier_nodeset(price, entries, "warn-world")
    options = NodeSetOptions(mode="live", label_order_guard="warn")

    with caplog.at_level(logging.WARNING):
        nodeset = make_intent_first_nodeset(
            label_nodeset.tail,
            "warn-world",
            symbol="ETHUSDT",
            price_node=price,
            options=options,
        )

    assert nodeset.name == "intent_first"
    assert any(
        "Label node output is connected to the order path" in record.message
        for record in caplog.records
    )
