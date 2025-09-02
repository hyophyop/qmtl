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

## Registry Integration (optional)

When `QMTL_SCHEMA_REGISTRY_URL` is set, components can resolve `schema_id`s via
an external Schema Registry. A lightweight in-memory client is available at
`qmtl/schema/registry.py` with a simple backward-compatibility check
(`is_backward_compatible`). Production deployments can swap in Confluent or
Redpanda clients.

## ControlBus CloudEvents — Protobuf Migration Path

ControlBus supports JSON today. A migration path to CloudEvents-over-Protobuf is
available via the placeholder codec in `qmtl/gateway/controlbus_codec.py` which
attaches `content_type=application/cloudevents+proto` and keeps a JSON payload
for compatibility. Consumers route based on the header and decode accordingly.
Rollout can proceed using dual publishing until all consumers understand the
new header.

{{ nav_links() }}
