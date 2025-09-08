---
title: "Schemas — Decision/Activation & Events"
tags: [reference, schemas]
author: "QMTL Team"
last_modified: 2025-08-29
---

{{ nav_links() }}

# Schemas — Decision/Activation & Events

- DecisionEnvelope: reference/schemas/decision_envelope.schema.json
- ActivationEnvelope: reference/schemas/activation_envelope.schema.json
- ActivationUpdated (event): reference/schemas/event_activation_updated.schema.json
- QueueUpdated (event): reference/schemas/event_queue_updated.schema.json
- PolicyUpdated (event): reference/schemas/event_policy_updated.schema.json
- Node (GSG): reference/schemas/node.schema.json
- World: reference/schemas/world.schema.json
- WorldNodeRef (WVG): reference/schemas/world_node_ref.schema.json
- Validation (WVG): reference/schemas/validation.schema.json
- DecisionEvent (WVG): reference/schemas/decision_event.schema.json
- OrderPayload: reference/schemas/order_payload.schema.json
- OrderAck: reference/schemas/order_ack.schema.json
- ExecutionFillEvent: reference/schemas/execution_fill_event.schema.json
- PortfolioSnapshot: reference/schemas/portfolio_snapshot.schema.json

## Node I/O Schemas

Standard DataFrame contracts ensure consistent columns, dtypes and timezone
handling between nodes. All schemas require a timezone-aware ``ts`` column in
UTC.

| Schema | Columns |
| ------ | ------- |
| ``bar`` | ``ts`` (UTC ``datetime64[ns]``), ``open`` ``float64``, ``high`` ``float64``, ``low`` ``float64``, ``close`` ``float64``, ``volume`` ``float64`` |
| ``quote`` | ``ts`` (UTC ``datetime64[ns]``), ``bid`` ``float64``, ``ask`` ``float64``, ``bid_size`` ``float64``, ``ask_size`` ``float64`` |
| ``trade`` | ``ts`` (UTC ``datetime64[ns]``), ``price`` ``float64``, ``size`` ``float64`` |

Example:

```python
import pandas as pd
from qmtl.schema import validate_schema

df = pd.DataFrame(
    {
        "ts": pd.date_range("2024-01-01", periods=1, tz="UTC"),
        "open": [1.0],
        "high": [1.0],
        "low": [1.0],
        "close": [1.0],
        "volume": [1.0],
    }
)

validate_schema(df, "bar")
```

## Registry Integration (optional)

When `QMTL_SCHEMA_REGISTRY_URL` is set, components can resolve `schema_id`s via
an external Schema Registry. A lightweight in-memory client is available at
`qmtl/schema/registry.py`. Production deployments can swap in Confluent or
Redpanda clients.

## ControlBus CloudEvents — Protobuf Migration Path

ControlBus supports JSON today. A migration path to CloudEvents-over-Protobuf is
available via the placeholder codec in `qmtl/gateway/controlbus_codec.py` which
attaches `content_type=application/cloudevents+proto` and keeps a JSON payload
for compatibility. Consumers route based on the header and decode accordingly.
Rollout can proceed using dual publishing until all consumers understand the
new header.

{{ nav_links() }}
