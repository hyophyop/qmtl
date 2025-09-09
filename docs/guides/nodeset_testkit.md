# Node Set Test Kit

Quick recipes for composing a Node Set behind a signal during tests and simulating fills via a fake webhook payload.

See the spec for Exchange Node Sets: ../architecture/exchange_node_sets.md

## Attach a minimal Node Set in tests

```python
from qmtl.sdk.node import Node
from qmtl.nodesets.base import NodeSetBuilder
from qmtl.nodesets.testkit import attach_minimal


def test_nodeset_attach_minimal():
    sig = Node(name="sig", interval=1, period=1)
    ns = attach_minimal(NodeSetBuilder(), sig, world_id="w1")
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
    # Each stub in the scaffold passes through the payload
    first = ns.head
    assert first is not None and len(list(ns)) == 7
```

## Create a fake fill webhook event

```python
from qmtl.nodesets.testkit import fake_fill_webhook


def test_fake_fill_webhook_shape():
    evt = fake_fill_webhook("AAPL", 1.0, 10.0)
    assert evt["specversion"] == "1.0" and evt["type"] == "trade.fill"
    assert evt["data"]["symbol"] == "AAPL" and evt["data"]["fill_price"] == 10.0
```

Notes
- The test kit emits CloudEvents‑shaped payloads for consistency with Gateway webhook ingestion.
- Minimal scaffolding uses stub nodes to establish contracts; concrete Node Sets replace them as implementations land.
