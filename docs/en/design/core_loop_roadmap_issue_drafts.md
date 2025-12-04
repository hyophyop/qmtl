---
title: "Core Loop Roadmap P0 Issue Drafts"
tags: [architecture, roadmap, issues, core-loop]
author: "QMTL Team"
last_modified: 2025-12-04
---

# Core Loop Roadmap P0 Issue Drafts

This file captures draft epics for the P0 milestones in `core_loop_roadmap.md`. Each item can be split into implementation/docs/test sub-issues as needed.

## Shared Guidelines

- Always state Program + Track/Milestone (P-0/P-A/B/C, T1–T6 P0–P2).
- Definition of done: code, docs, and tests are updated together, and architecture As-Is/To-Be stay consistent.
- Default-safe, WS SSOT, and ExecutionDomain rules must not be broken without an ADR/waiver that records the exception and follow-up plan.

## P0 Draft Issues

### 1. T1 P0‑M1 — Normalize SubmitResult and Align with Core Loop

- Program: P-A (Core Loop Paved Road)
- Track/Milestone: T1 P0-M1
- Goal: Normalize Runner.submit/CLI output to be isomorphic with `DecisionEnvelope`/`ActivationEnvelope`, providing a single result for “submit → evaluate.”
- Outputs: New `SubmitResult`/CLI output format, shared WS schema module, refreshed guides (`strategy_workflow.md`, `sdk_tutorial.md`).
- Scope/Tasks: Hide SDK-only fields, standardize failures/warnings, update sample outputs/docs.
- DOD/Tests: Add SubmitResult snapshots to Core Loop contract tests; ensure WS/SDK type compatibility in CI.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), [worldservice.md](../architecture/worldservice.md)

### 2. T1 P0‑M2 — Remove/Normalize Execution Mode & Domain Hints

- Program: P-A (Core Loop Paved Road)
- Track/Milestone: T1 P0-M2
- Goal: Remove SDK-side ExecutionDomain selection; only WS decisions are allowed.
- Outputs: Stricter validation for `execution_domain`/`mode`, deprecation notice for non-backtest modes, cleaned docs.
- Scope/Tasks: Tighten Runner/CLI parameter validation, codify default-safe downgrades, update guides/tutorials.
- DOD/Tests: Contract tests for downgrade/reject cases; CLI/SDK help updated.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md)

### 3. T2 P0‑M1 — Unify Evaluation/Activation Flow

- Program: P-A (Evaluation/Activation Unification)
- Track/Milestone: T2 P0-M1
- Goal: Make WS the sole source for final activation/weights/contribution; separate ValidationPipeline outputs as pre-checks.
- Outputs: Cleaned WS result exposure in SubmitResult/CLI/API, separated ValidationPipeline outputs, updated ops/dev guides.
- Scope/Tasks: Share WS API schema, adjust Runner output composition, document WS SSOT principle.
- DOD/Tests: Remove mixed WS/ValidationPipeline paths; add activation exposure checks to contract tests.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [worldservice.md](../architecture/worldservice.md)

### 4. T2 P0‑M2 — ExecutionDomain/effective_mode Rule Alignment

- Program: P-A (Evaluation/Activation Unification)
- Track/Milestone: T2 P0-M2
- Goal: Enforce compute-only downgrade when WS API receives missing/ambiguous ExecutionDomain and reflect the rule consistently in code/docs.
- Outputs: WS request validation/errors, SDK/CLI downgrade messages, rule documentation.
- Scope/Tasks: Harden WS request schema validation, remove Runner submission hints, add default-safe tests.
- DOD/Tests: E2E tests for compute-only downgrade; legacy modes removed from docs.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [worldservice.md](../architecture/worldservice.md), [gateway.md](../architecture/gateway.md)

### 5. T3 P0‑M1 — World-Based Data Preset On-Ramp

- Program: P-A (Data Preset), P-C (Data Autopilot)
- Track/Milestone: T3 P0-M1
- Goal: Define world/preset → data preset mapping and let Runner/CLI auto-provision Seamless instances.
- Outputs: World preset spec, Runner/CLI preset wiring, updated examples/guides.
- Scope/Tasks: Add preset section to `world/world.md`, automate Seamless setup, retire direct `history_provider` setup paths.
- DOD/Tests: E2E test for preset-driven Seamless injection; example runs validated.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md), [world.md](../world/world.md)

### 6. T4 P0‑M1 — Align ComputeContext/ExecutionDomain Rules

- Program: P-A (ComputeContext Alignment)
- Track/Milestone: T4 P0-M1
- Goal: Make Gateway/DM/SDK consume `compute_context.py` rules consistently and enforce WS-decision priority.
- Outputs: Gateway/DAG Manager context refactors, submission meta validation, rule documentation.
- Scope/Tasks: Apply WS decision/ExecutionDomain priority, standardize as_of/ComputeKey handling, add explicit errors/metrics on violations.
- DOD/Tests: ComputeContext contract tests; confirm WS decision is never bypassed.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [gateway.md](../architecture/gateway.md), [dag-manager.md](../architecture/dag-manager.md)

### 7. T4 P0‑M2 — Guarantee NodeID/TagQuery Determinism

- Program: P-A (ComputeContext Alignment)
- Track/Milestone: T4 P0-M2
- Goal: Ensure TagQueryNode extensions keep NodeID stable via shared determinism rules across layers.
- Outputs: NodeID generation rules/tests, shared validation in DAG Manager/Gateway/SDK, observability metrics.
- Scope/Tasks: Document NodeID/TagQuery rules, add determinism tests, emit alerts/logs on drift.
- DOD/Tests: Determinism regression tests (same input → same NodeID); observability dashboard wired.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [dag-manager.md](../architecture/dag-manager.md), [gateway.md](../architecture/gateway.md)

### 8. T5 P0‑M1 — Close the Determinism Checklist

- Program: P-B (Determinism)
- Track/Milestone: T5 P0-M1
- Goal: Implement/verify the Determinism checklist from `architecture.md` (NodeID CRC, NodeCache GC, TagQuery stability, etc.) to secure Core Loop determinism.
- Outputs: Implemented checklist items, ops checks/metrics, updated runbooks.
- Scope/Tasks: Harden determinism-related code, verify GC/cache policies, add observability signals, refresh ops docs.
- DOD/Tests: Determinism regressions pass; metrics visible in ops dashboards.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), [operations/monitoring.md](../operations/monitoring.md)

### 9. T6 P0‑M1 — Core Loop Contract Test Suite

- Program: P-A (Core Loop Contract Tests)
- Track/Milestone: T6 P0-M1
- Goal: Add a fast contract test suite covering “submit → evaluate/activate → safe execution/gating → observe results.”
- Outputs: `tests/e2e/core_loop` skeleton, cases for SubmitResult/ExecutionDomain/TagQuery stability, CI integration.
- Scope/Tasks: Implement happy-path and downgrade cases, simplify fixtures, add usage notes to docs.
- DOD/Tests: Suite passes in CI; merge-blocking rule documented; cross-links to architecture docs added.
- Dependencies/Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), [tests](../../tests)
