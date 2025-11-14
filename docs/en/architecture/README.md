---
title: "Architecture"
tags:
  - architecture
  - overview
author: "QMTL Team"
last_modified: 2025-09-12
---

{{ nav_links() }}

# Architecture

!!! abstract "TL;DR"
    High-level hub for QMTL's architectural components. Use the links below to explore each module.

Design documents describing core QMTL components.

See also: Architecture Glossary (../architecture/glossary.md) for canonical terms such as DecisionEnvelope, ActivationEnvelope, ControlBus, and EventStreamDescriptor.

## Related Documents
- [Architecture Overview](architecture.md): High-level system design.
- [Gateway](gateway.md): Gateway component specification.
- [DAG Manager](dag-manager.md): DAG Manager design.
- [WorldService](worldservice.md): World policy, decisions, activation.
- [ControlBus](controlbus.md): Internal control bus (opaque to SDK).
- [Lean Brokerage Model](lean_brokerage_model.md): Brokerage integration details.
- [Control-Plane Radon Plan](radon_control_plane.md): Roadmap for Gateway and DAG Manager complexity remediation.

## Architectural Layers at a Glance

QMTL's control plane is composed of a small set of layered services. Each layer narrows
the concerns of the layer beneath it and exposes a specific contract to clients and
operators.

1. **Gateway** - Edge ingress for SDKs and automations. Normalises client requests,
   enforces authentication, and proxies to downstream domain services.
2. **DAG Manager** - System of record for orchestration DAGs. Owns versioned plan
   storage, dependency resolution, execution queueing, and topic namespace policy.
3. **WorldService** - Domain policy execution. Manages world state, activation windows,
   and strategy-to-world bindings surfaced through the Gateway.
4. **ControlBus** - Internal event fabric that delivers control-plane signals between
   Gateway, DAG Manager, and operators. Generally opaque to SDK consumers.
5. **Integrations Layer** - Adapters for brokerages, exchanges, and observability
   sinks. Extends the core services without modifying their contracts.

Diagram-style deep dives for each component live in the linked documents above.

## Operations Quickstart

Startup and configuration validation workflows are documented in the operations
guides. When you need a hands-on walkthrough, follow these step-by-step
playbooks:

- [Backend Quickstart](../operations/backend_quickstart.md#fast-start-validate-and-launch)
- [Operations Config CLI](../operations/config-cli.md)

{{ nav_links() }}
