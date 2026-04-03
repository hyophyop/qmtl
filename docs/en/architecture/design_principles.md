---
title: "QMTL Design Principles"
tags:
  - architecture
  - design
author: "QMTL Team"
last_modified: 2026-03-06
---

{{ nav_links() }}

# QMTL Design Principles

## Related Documents

- [Architecture Overview](architecture.md)
- [Capability Map](capability_map.md)
- [Semantic Types](semantic_types.md)
- [Decision Algebra](decision_algebra.md)
- [Architecture Glossary](glossary.md)

## Purpose

QMTL is not intended to be a framework dedicated to a single strategy archetype.
Its purpose is to provide a **strictly composable system** that does not collapse into
an accumulation of special cases as new strategy styles, learning styles, and execution
styles are introduced.

Accordingly, the design of QMTL must do more than explain the current feature set.
Whenever a new feature is proposed, the architecture should be able to answer the
following questions in a stable way:

- Does this feature compose naturally with existing capabilities?
- Does composition require combination-specific exceptions?
- Are constraints explained by semantics rather than feature names?
- Can the feature be added as a new contract without weakening core rules?

If the architecture repeatedly answers those questions with “exceptionally yes,” that
should be treated as a design flaw rather than a temporary limitation.

## First-Class Rules

### 1. Capability-first

Concept ID: `PRIN-CAPABILITY-FIRST`

The first-class concepts in QMTL are not archetypes such as `directional`, `ML`, or
`market making`, but independent capabilities such as:

- observation
- feature extraction
- labeling
- inference
- decision
- execution planning
- execution state
- risk/policy

Strategy archetypes must be described only as compositions of those capabilities, not
as the organizing axis of the core design.

### 2. Composition Over Exceptions

Concept ID: `PRIN-COMPOSITION-OVER-EXCEPTIONS`

Feature combinations are the default usage pattern, not special cases.
Combinations such as `ML + Market Making`, `Rule-based + Quote Planning`, and
`Labeling + Offline Replay` must be explainable as ordinary compositions of existing
capabilities.

If a feature requires branches such as the following, the design should be revisited:

- `if strategy_type == ...`
- `if mm_enabled and ml_enabled`
- combination-specific rules across domain/strategy kinds

### 3. Constraints Must Come From Semantics

Concept ID: `PRIN-SEMANTIC-CONSTRAINTS`

If a composition is forbidden, the reason must not be “because it is ML” or
“because it is MM.” It must come from the semantics of values and stages.

Examples:

- values containing future information cannot enter a live decision path
- mutable execution state cannot be shared across domains
- only immutable artifacts may be reused across domains in a reproducible way

Constraints should therefore be expressed in terms of semantic types, not feature names.

### 4. Core Neutrality

Concept ID: `PRIN-CORE-NEUTRALITY`

The Core must not implicitly privilege one strategy style.
If directional strategies are implemented first and all execution concepts become
permanently order-centric, later additions such as `quote`, `inventory`, and
`cancel/replace` will distort the architecture.

The Core should not be the structure that best explains one strategy class.
It should be the structure that can admit multiple execution forms with equal rigor.

### 5. Explicit Research/Execution Boundaries

Concept ID: `PRIN-EXPLICIT-BOUNDARIES`

QMTL may support research, evaluation, and execution together, but it must not
blend values from those boundaries implicitly.

The following boundaries must always remain explicit:

- causal vs delayed
- replay-only vs live-safe
- immutable artifact vs mutable state
- decision output vs execution state

When those boundaries blur, leakage and combination-specific rules grow over time.

### 6. Extension Adds Contracts

Concept ID: `PRIN-EXTENSION-ADDS-CONTRACTS`

Good extensions do not increase branching in existing flows.
Instead, they add new semantic types, new decision subtypes, new planners, or new
adapters while preserving the existing stage contracts.

Whenever possible, a new feature should first be explained as a new role inside the
existing capability graph, not as a new top-level mode or archetype enum.

### 7. Profiles Are Examples

Concept ID: `PRIN-PROFILES-ARE-EXAMPLES`

Profiles such as `ML-driven MM`, `directional trend`, or `label research` are useful
for documentation and onboarding, but they are not first-class concepts that define
core type boundaries or service contracts.

The number of profiles may grow; the number of core rules should not.

## Design Review Checklist

When adding or changing a feature, review it in the following order:

1. Which capability does this feature belong to?
2. What semantic types does it consume and produce?
3. Can it compose with existing capabilities without adding a special case?
4. If there is a restriction, can it be described semantically rather than by feature name?
5. Does this feature extend the system by adding a contract, or by bending the Core?

If questions 3 and 4 repeatedly fail, adjust the capability boundaries or semantic
contracts before changing the implementation.

## Non-goals

QMTL does not aim to force every strategy into a single uniform execution model.
Instead, it aims to let different strategies coexist and compose under shared
capabilities and semantic contracts.

The priority is therefore not “making everything look the same,” but
“making everything composable under the same rules.”

{{ nav_links() }}
