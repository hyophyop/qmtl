---
title: "Architecture"
tags:
  - architecture
  - overview
author: "QMTL Team"
last_modified: 2025-12-15
---

{{ nav_links() }}

# Architecture

!!! abstract "TL;DR"
    High-level hub for QMTL's architectural components. Use the links below to explore each module.

Design documents describing core QMTL components.

See also: Architecture Glossary (../architecture/glossary.md) for canonical terms such as DecisionEnvelope, ActivationEnvelope, ControlBus, and EventStreamDescriptor.

## Doc Map

### Overview
- [Architecture Overview](architecture.md): High-level system blueprint and Core Loop alignment.
- [Glossary](glossary.md): Canonical terms such as DecisionEnvelope and ExecutionDomain.

### Control plane
- [Gateway](gateway.md): Public ingress, proxy/caching, and stream relay.
- [DAG Manager](dag-manager.md): Graph/node/queue SSOT, diffs, and orchestration.
- [WorldService](worldservice.md): World policy, decisions, activation, allocations/rebalancing.
- [ControlBus](controlbus.md): Internal control-plane event fabric (Activation/Queue/Policy).

### Data plane
- [Seamless Data Provider v2](seamless_data_provider_v2.md): Conformance, backfill, SLAs, observability.
- [CCXT × Seamless Integrated](ccxt-seamless-integrated.md): CCXT-backed history/live delivery through Seamless.

### Execution & brokerage
- [Exchange Node Sets](exchange_node_sets.md): Composable execution-layer Node Sets.
- [Execution Layer Nodes](execution_nodes.md): Pre-trade/sizing/execution/fills/risk/timing nodes.
- [Execution State & TIF](execution_state.md): Order state machine and TIF semantics.
- [Lean Brokerage Model](lean_brokerage_model.md): Brokerage integration details.

### Risk
- [Risk Signal Hub](risk_signal_hub.md): Portfolio/risk snapshot SSOT.

### Templates
- [Layered Template System](layered_template_system.md): Project/template layering architecture.

### Engineering notes
- [SDK Layering](../maintenance/engineering/sdk_layers.md): SDK dependency layering guide.
- [Seamless Data Provider Modularization](../maintenance/engineering/seamless_data_provider_modularity.md): SDP refactor/module-boundary memo.
- [RPC Adapter Command/Facade Design](../maintenance/engineering/rpc_adapters.md): Adapter complexity reduction patterns.

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
