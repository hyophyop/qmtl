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

## ControlBus CloudEvents — Protobuf Migration Path

ControlBus supports JSON today. A migration path to CloudEvents-over-Protobuf is
available via the placeholder codec in `qmtl/services/gateway/controlbus_codec.py` which
attaches `content_type=application/cloudevents+proto` and keeps a JSON payload
for compatibility. Consumers route based on the header and decode accordingly.
Rollout can proceed using dual publishing until all consumers understand the
new header.

{{ nav_links() }}
