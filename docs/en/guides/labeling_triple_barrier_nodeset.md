# Triple-Barrier Labeling NodeSet Recipe

Use the `labeling_triple_barrier` recipe to generate Triple-Barrier labels with the **same NodeSet implementation** across **offline training/evaluation** and **live/paper** usage. The recipe emits labels only on a **delayed output stream**, keeping them isolated from the order/decision path. See the [Labeling contract](../design/labeling_contract.md) for leakage guardrails.

## Port specification

- Inputs
  - `price`: price observations in the form `{"observed_time": datetime, "price": float, "symbol": str?}`
  - `entry_events`: entry events in the form `{"entry_time": datetime, "entry_price": float, "side": str, "barrier": BarrierSpec|dict, "horizon": HorizonSpec|dict}`
- Outputs
  - `labels`: list of `TripleBarrierLabel` objects (delayed label stream)

> Labels are never emitted at `entry_time=t`; they appear only after `resolved_time=t*`.
> Use distinct nodes for `price` and `entry_events`.

## Offline training/evaluation example

```python
from datetime import datetime, timedelta, timezone

from qmtl.runtime.labeling import BarrierMode, BarrierSpec, HorizonSpec
from qmtl.runtime.nodesets.recipes import make_labeling_triple_barrier_nodeset
from qmtl.runtime.sdk import StreamInput

price = StreamInput(tags=["price"], interval="1m", period=500)
entry_events = StreamInput(tags=["entry_events"], interval="1m", period=500)

nodeset = make_labeling_triple_barrier_nodeset(
    price,
    entry_events,
    world_id="train",
    barrier=BarrierSpec(
        profit_target=0.02,
        stop_loss=0.01,
        mode=BarrierMode.RETURN,
    ),
    horizon=HorizonSpec(max_bars=30),
)

strategy.add_nodes([price, entry_events, nodeset])

entry_payload = {
    "entry_time": datetime.now(timezone.utc),
    "entry_price": 100.0,
    "side": "long",
    "symbol": "AAPL",
}
```

The label stream is available at `nodeset.tail`; connect it to your offline label store or training data pipeline.

## Live/paper example

```python
from qmtl.runtime.nodesets.recipes import make_labeling_triple_barrier_nodeset

label_nodeset = make_labeling_triple_barrier_nodeset(
    price_node,
    entry_events_node,
    world_id="live-world",
    barrier=barrier_spec,
    horizon=horizon_spec,
)

# Labels are for monitoring/reporting/post-hoc data ingestion only
monitoring_sink.add_input(label_nodeset.tail)
```

> Do not connect label outputs to order/decision inputs. Use the same NodeSet but keep the label stream isolated to prevent leakage.
