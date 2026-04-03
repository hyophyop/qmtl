---
title: "QMTL Documentation System and Layer Separation"
tags:
  - architecture
  - documentation
  - design
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL Documentation System and Layer Separation

## Related documents

- [Architecture Overview](README.md)
- [QMTL Design Principles](design_principles.md)
- [QMTL Implementation Traceability](implementation_traceability.md)
- [Docs Internationalization](../guides/docs_internationalization.md)
- [Backend Quickstart](../operations/backend_quickstart.md)

## Purpose

QMTL documentation has grown while trying to answer four different questions at once:

- What design rules are normative?
- What is the simplest contract a user needs to know?
- What operational procedures must operators follow?
- How much of the design is implemented today?

All four are important, but they do different jobs. When they are mixed in one page, readers can no longer cleanly distinguish:

- long-lived norms from current implementation detail
- simple user-facing contracts from operator-only procedures
- product surface from internal service structure
- target design from current implementation state

This document defines an information architecture for separating QMTL documents by purpose.

## Problem statement

The main issue is not that QMTL has many documents. The issue is that document roles are mixed.

- Normative architecture pages include current implementation notes, deprecated warnings, and operational quickstarts.
- The simple Core Loop contract is described together with approvals, audits, and rebalancing operations.
- Design-principle pages and implementation-state pages are close to each other, but readers do not learn the distinction first.
- Operational rules can read like architecture law, while architecture law can read like a temporary operational policy.

## Goals

- Keep norms short and stable.
- Separate the user golden path from operator procedures.
- Keep implementation status in a dedicated layer.
- Make each document answer a single primary question.

## Non-goals

- Rewriting every document immediately
- Removing cross-links between design and operations
- Splitting the docs into tiny fragments with no useful narrative

## Documentation layers

### 1. Principles

Question: “What kinds of design decisions does QMTL consider correct?”

- Content:
  - stable design rules
  - capability-first, semantic boundaries, default-safe
  - extension criteria for future features
- Includes:
  - [QMTL Design Principles](design_principles.md)
  - [QMTL Capability Map](capability_map.md)
  - [QMTL Semantic Types](semantic_types.md)
  - [QMTL Decision Algebra](decision_algebra.md)
- Excludes:
  - current API inventories
  - current implementation status
  - operational procedures

### 2. Normative Architecture

Question: “What are the service boundaries, SSOTs, and protocol contracts?”

- Content:
  - service ownership and SSOT boundaries
  - state transitions and envelope contracts
  - formal interfaces across control, data, and execution planes
- Includes:
  - [Gateway](gateway.md)
  - [DAG Manager](dag-manager.md)
  - [WorldService](worldservice.md)
  - [ControlBus](controlbus.md)
  - [Risk Signal Hub](risk_signal_hub.md)
  - [Execution State](execution_state.md)
- Excludes:
  - deployment procedures
  - planned/partial/implemented labels
  - onboarding-oriented walkthroughs

### 3. Product Contracts

Question: “What is the minimum contract that a user or higher-level client needs to know?”

- Content:
  - golden paths such as `Runner.submit(..., world=...)`
  - user-visible result contracts
  - simple phase models, approval checkpoints, and read-only observation surfaces
- Includes examples:
  - Core Loop contract pages
  - world campaign loop contracts
  - allocation/apply product flows
- Excludes:
  - internal implementation classes
  - operator-only tuning details
  - experimental schema negotiation switches

### 4. Operations

Question: “How do operators deploy, monitor, approve, and recover the system?”

- Content:
  - deployment, monitoring, approvals, incidents, rollout, audit
  - CLI runbooks, observability, SLOs, failure handling
- Includes:
  - `docs/operations/`
- Excludes:
  - core semantic rules
  - user-facing product promises

### 5. Implementation Status

Question: “How much of the target design exists in code today?”

- Content:
  - traceability mappings
  - planned/partial/implemented status
  - representative code and test evidence
- Includes:
  - [QMTL Implementation Traceability](implementation_traceability.md)
- Excludes:
  - new normative claims
  - operational procedures

### 6. Migration & Deprecation

Question: “How do readers move from the old path to the new path?”

- Content:
  - deprecated warnings
  - breaking-change guides
  - moved pages and old-to-new links
- Includes:
  - `guides/migration_*`
  - moved marker pages
- Excludes:
  - long-lived architecture norms
  - runbook content

## Authoring rules

Each document should make three things clear within the first 30 seconds:

1. What question does this page answer?
2. Who is it for?
3. Is it normative, operational, or status-oriented?

Recommended rules:

- Use the opening summary or purpose section to state the page question explicitly.
- Normative pages should not explain implementation status at length. Link to [QMTL Implementation Traceability](implementation_traceability.md) instead.
- Operational pages should not redefine architecture principles. Link to the normative pages when needed.
- Product-contract pages should keep advanced operator paths out of the main flow.
- moved/deprecated pages should stay short and mainly point to the current page.
- Any page that is intentionally off-nav (moved marker, icebox draft, or locale-incomplete note) should be listed under `not_in_nav` in `mkdocs.yml` so it is treated as an explicitly hidden page rather than accidental navigation debt.

## Recommended top-level structure

```text
Getting Started
Product Contracts
Architecture
  Principles
  Normative Architecture
Operations
Implementation Status
Maintenance
Migration
```

The current `Architecture` section is still useful, but it effectively contains part of the Product Contracts and Implementation Status layers. Over time, those should be separated more explicitly.

## Proposed reclassification of current pages

### Keep as-is

- `design_principles.md` -> Principles
- `capability_map.md` -> Principles
- `semantic_types.md` -> Principles
- `decision_algebra.md` -> Principles
- `gateway.md`, `dag-manager.md`, `worldservice.md`, `controlbus.md` -> Normative Architecture
- `implementation_traceability.md` -> Implementation Status
- `operations/*` -> Operations

### Split recommended

- `architecture.md`
  - Keep: high-level system shape, layer boundaries, minimal normative Core Loop contract
  - Move out: deployment profiles, deprecated warnings, operational quickstarts, migration-oriented notes
- `core_loop_world_automation.md`
  - Keep: user/product-facing Core Loop contract
  - Move out: scheduler operation, operator approval details, execution runbook specifics

### Move candidates

- moved pages such as `architecture/sdk_layers.md` should remain maintenance-only references.
- approval and audit-heavy pages fit better under `operations/` than under `architecture/`.

## Link direction rules

Prefer this direction of reference:

```text
Principles
  -> Normative Architecture
    -> Product Contracts
      -> Operations
        -> Implementation Status
```

Reverse links are allowed, but the main explanation should not depend on them.

Examples:

- Principles pages should not explain runbooks.
- Runbooks should link to normative contracts instead of redefining them.
- Implementation-status pages should not modify architecture rules; they only report current coverage.

## Proposed metadata

Over time, QMTL can introduce the following front matter fields:

- `doc_role`: `principles | normative-architecture | product-contract | operations | implementation-status | migration`
- `audience`: `author | operator | contributor | reviewer`
- `normative`: `true | false`

These can start as conventions before they become tooling inputs.

## Migration Progress (2026-04)

- Completed
  - Applied the first architecture split so `architecture.md` and `worldservice.md` point outward for product contracts, operations, and implementation status instead of carrying all of that inline.
  - Fixed the Core Loop golden path in [Core Loop Contract](../contracts/core_loop.md) and [World Lifecycle Contract](../contracts/world_lifecycle.md).
  - Split `core_loop_world_automation.md` so user-facing contract and operator/runbook concerns no longer share the same main narrative.
  - Extended `implementation_traceability.md` with control-plane and governance concepts.
  - Moved Gateway/DAG Manager/ControlBus/Risk Signal Hub runtime procedures into `operations/` pages.
- In progress
  - Slimming the top normative specs (`architecture.md`, `gateway.md`, `dag-manager.md`) further so CLI, rollout, and config procedures stay in operations pages.
  - Reorganizing nav around `Architecture / Product Contracts / Operations / Design / Archive`, with the Design section exposing an [Icebox index](../design/icebox.md) instead of individual draft pages.
  - Moving intentionally unpublished pages to explicit `not_in_nav` entries.
  - Keeping locale-incomplete material off-nav until the `ko` and `en` pair exists, then promoting only the documents that are ready for the official information architecture.
- Remaining
  - Move more examples/appendices/operational detail out of large normative pages.
  - Expose the Implementation Status and Migration layers more explicitly in navigation.
  - Periodically reclassify design/archive/maintenance pages so the public doc surface stays intentional.

## Completion criteria

The documentation split is meaningfully complete when:

- readers can immediately tell whether a page is normative or status-oriented
- the `Runner.submit` contract and operator procedures live on separate paths
- implementation status no longer requires reading normative pages
- readers can learn the design rules without also learning temporary implementation exceptions

{{ nav_links() }}
