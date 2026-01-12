from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec, LabelOutcome
from qmtl.runtime.nodesets.recipes import (
    LABELING_TRIPLE_BARRIER_DESCRIPTOR,
    make_labeling_triple_barrier_nodeset,
)
from qmtl.runtime.nodesets.testkit import make_cloudevent
from qmtl.runtime.sdk import Node


def test_labeling_triple_barrier_nodeset_emits_delayed_label():
    price = Node(name="price_input", interval=60, period=10, config={"stream": "price"})
    entries = Node(name="entry_input", interval=60, period=10, config={"stream": "entries"})
    barrier = BarrierSpec(
        profit_target=0.01,
        stop_loss=0.01,
        mode=BarrierMode.RETURN,
    )
    horizon = HorizonSpec(max_bars=3)

    nodeset = make_labeling_triple_barrier_nodeset(
        price,
        entries,
        world_id="w1",
        barrier=barrier,
        horizon=horizon,
    )

    description = nodeset.describe()
    assert description["ports"]["inputs"][0]["name"] == "price"
    assert description["ports"]["inputs"][1]["name"] == "entry_events"
    assert description["ports"]["outputs"][0]["name"] == "labels"
    assert nodeset.descriptor is LABELING_TRIPLE_BARRIER_DESCRIPTOR

    entry_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    entry_payload = {
        "entry_time": entry_time,
        "entry_price": 100.0,
        "side": "long",
        "symbol": "AAPL",
    }
    entry_event = make_cloudevent("label.entry", "qmtl.test", entry_payload)
    label_node = nodeset.tail

    label_node.cache.append(entries.node_id, entries.interval, 0, entry_event["data"])
    assert label_node.compute_fn(label_node.cache.view()) is None

    label_node.cache.append(
        price.node_id,
        price.interval,
        0,
        {"observed_time": entry_time, "price": 101.0, "symbol": "AAPL"},
    )
    assert label_node.compute_fn(label_node.cache.view()) is None

    label_node.cache.append(
        price.node_id,
        price.interval,
        1,
        {
            "observed_time": entry_time + timedelta(minutes=1),
            "price": 101.0,
            "symbol": "AAPL",
        },
    )
    labels = label_node.compute_fn(label_node.cache.view())
    assert labels is not None
    assert labels[0].outcome == LabelOutcome.PROFIT_TARGET
