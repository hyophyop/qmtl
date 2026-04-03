---
title: "QMTL Semantic Types"
tags:
  - architecture
  - design
author: "QMTL Team"
last_modified: 2026-03-06
---

{{ nav_links() }}

# QMTL Semantic Types

## Related Documents

- [QMTL Design Principles](design_principles.md)
- [QMTL Capability Map](capability_map.md)
- [Decision Algebra](decision_algebra.md)
- [Architecture Glossary](glossary.md)

## Purpose

Constraints in QMTL must not come from feature names or strategy archetypes.
They must come from the semantics of values and states, and the system should use
those semantics to determine what can or cannot connect.

This document defines the semantic types used as that design criterion.

## Core Axes

A QMTL semantic type must make the following axes explicit:

- causality: `causal` or `delayed`
- mutability: `immutable` or `mutable`
- scope: `global`, `world-scoped`, or `domain-scoped`
- replay legality: `replay-safe`, `live-safe`, or `replay-only`
- actuation: `passive`, `decision`, or `command`

Any new value family should be explainable on these axes before it is implemented.

## Base Semantic Types

### CausalStream

Concept ID: `SEM-CAUSAL-STREAM`

A stream containing only information available up to the current point in time.
This is the default input type for feature extraction, inference, and live decision paths.

Examples:

- quotes
- trades
- order book snapshots
- current portfolio observations
- causal features

### DelayedStream

Concept ID: `SEM-DELAYED-STREAM`

A stream containing future information or ex-post interpretation.
It may be used for training and evaluation, but it must not directly feed a live
decision path.

Examples:

- triple-barrier label outputs
- realized future returns
- ex-post attribution labels

### ImmutableArtifact

Concept ID: `SEM-IMMUTABLE-ARTIFACT`

A reproducible, read-only output stored for later reuse.
Feature artifacts, label artifacts, dataset snapshots, and trained model references
belong to this family.

Core properties:

- content-addressable or fingerprint-bound
- may be read across domains
- must not contain mutable execution state

### MutableExecutionState

Concept ID: `SEM-MUTABLE-EXECUTION-STATE`

State that changes during execution.
Portfolio, open orders, open quotes, inventory, and route acknowledgements belong here.

Core properties:

- world/domain scoped
- not shareable across domains
- tightly coupled to live operational correctness

### DecisionValue

Concept ID: `SEM-DECISION-VALUE`

A value expressing execution intent.
Scores, directional outputs, position targets, order intents, and quote intents are all
members of this family.

A DecisionValue must be derived from `CausalStream` and/or `ImmutableArtifact`.
It must not be directly derived from `DelayedStream`.

### CommandValue

Concept ID: `SEM-COMMAND-VALUE`

A value that requests real action from an external system.
Order submission, cancel/replace, and rebalance application belong here.

CommandValue may only be produced after planning and policy gates.

## Connection Legality Rules

The following rules hold regardless of archetype.

| From | To | Allowed | Reason |
| --- | --- | --- | --- |
| CausalStream | Inference | yes | causal input |
| DelayedStream | Inference(live path) | no | future-information leakage |
| DelayedStream | Dataset Build | yes | research/evaluation only |
| ImmutableArtifact | Inference | yes | reproducible read-only input |
| MutableExecutionState | Cross-domain reuse | no | violates domain isolation |
| DecisionValue | Planner | yes | shared execution-planning boundary |
| CommandValue | Direct feature input | no | execution side effects must not flow back as features directly |

## World/Domain Rules

### Only ImmutableArtifact May Be Shared

Cross-domain reuse is limited to immutable artifacts.
Execution caches and execution state remain world/domain scoped.

### Mutable State Is Bound to SSOT Boundaries

MutableExecutionState is tied to world/domain and service ownership boundaries.
Even when two objects look similar, they should not be treated as the same object
across SSOT boundaries.

### Replay Legality Must Be Declared at the Type Level

Whether a value is replay-only or live-safe should not be decided ad hoc at call time.
It should be part of the value's semantic contract.

## Procedure for Adding a New Type

Before adding a new semantic type or value family, document the following:

1. Is it causal or delayed?
2. Is it immutable or mutable?
3. What is its world/domain scope?
4. Is it live-safe or replay-only?
5. Is it an artifact, state, decision, or command?

If those questions cannot be answered clearly, the semantic contract should be
completed before implementation proceeds.

## Design Standard

A good design satisfies the following:

- restrictions can be explained by semantic type rather than strategy name
- new features are absorbed into a legality matrix rather than new exception trees
- combinations like `ML + MM` work without special handling as long as semantic types match

Bad design signals include:

- `if strategy_type == "mm"` decides legality
- `if live and ml and labels` style combination exceptions
- payload shape determines legality more than semantics do

{{ nav_links() }}
