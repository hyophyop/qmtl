---
title: "Schemas — Decision/Activation & Events"
tags: [reference, schemas]
author: "QMTL Team"
last_modified: 2026-03-06
---

{{ nav_links() }}

# Schemas — Decision/Activation & Events

- DecisionEnvelope: reference/schemas/decision_envelope.schema.json
- ActivationEnvelope: reference/schemas/activation_envelope.schema.json
- ActivationUpdated (event): reference/schemas/event_activation_updated.schema.json
- QueueUpdated (event): reference/schemas/event_queue_updated.schema.json
- QueueLifecycle (event): reference/schemas/event_queue_lifecycle.schema.json
- PolicyUpdated (event): reference/schemas/event_policy_updated.schema.json
- Node (GSG): reference/schemas/node.schema.json
- World: reference/schemas/world.schema.json
- WorldNodeRef (WVG): reference/schemas/world_node_ref.schema.json
- Validation (WVG): reference/schemas/validation.schema.json
- DecisionsRequest (WVG): reference/schemas/decisions_request.schema.json
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
| ``bar`` | ``ts`` (UTC ``Datetime(time_unit='ns', time_zone='UTC')``), ``open`` ``Float64``, ``high`` ``Float64``, ``low`` ``Float64``, ``close`` ``Float64``, ``volume`` ``Float64`` |
| ``quote`` | ``ts`` (UTC ``Datetime(time_unit='ns', time_zone='UTC')``), ``bid`` ``Float64``, ``ask`` ``Float64``, ``bid_size`` ``Float64``, ``ask_size`` ``Float64`` |
| ``trade`` | ``ts`` (UTC ``Datetime(time_unit='ns', time_zone='UTC')``), ``price`` ``Float64``, ``size`` ``Float64`` |

Example:

```python
import polars as pl
from qmtl.foundation.schema import validate_schema

df = pl.DataFrame(
    {
        "ts": pl.datetime_range(
            "2024-01-01",
            "2024-01-01",
            interval="1d",
            eager=True,
            time_unit="ns",
            time_zone="UTC",
        ),
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

When `connectors.schema_registry_url` is set in `qmtl.yml` (or the legacy
`QMTL_SCHEMA_REGISTRY_URL` environment variable is provided), components can
resolve `schema_id`s via an external Schema Registry. A lightweight in-memory
client is available at `qmtl/foundation/schema/registry.py`. Production
deployments can swap in Confluent or Redpanda clients.

## ControlBus Event Encoding

The public Gateway ControlBus contract is JSON-only. Events are exchanged as
UTF-8 JSON objects, and the public schema surface does not define a
CloudEvents-over-Protobuf variant or `application/cloudevents+proto` content
negotiation path.

{{ nav_links() }}
