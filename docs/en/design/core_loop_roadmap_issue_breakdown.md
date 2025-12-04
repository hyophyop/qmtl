---
title: "Core Loop Roadmap P0 Issue Breakdown"
tags: [architecture, roadmap, issues, core-loop]
author: "QMTL Team"
last_modified: 2025-12-04
---

# Core Loop Roadmap P0 Issue Breakdown

This splits the 9 P0 epics from `core_loop_roadmap_issue_drafts.md` into sub-issues that can be executed independently while staying within the context of `core_loop_roadmap.md` (Program/Track/Milestone).

## T1 P0-M1 — Normalize SubmitResult

1) Schema alignment & sharing  
- Define `SubmitResult` ↔ `DecisionEnvelope/ActivationEnvelope` field mapping; move to a shared WS/SDK types module.  
- Outputs: schema module, compatibility tests.

2) SDK/CLI output cleanup  
- Hide non-user fields, standardize failure/warning messages, refresh sample outputs.  
- Outputs: updated CLI/SDK output, snapshot tests.

3) Docs/guides update  
- Rewrite `strategy_workflow.md` and `sdk_tutorial.md` around the Core Loop flow.  
- Outputs: refreshed guides and examples.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [core_loop_roadmap_issue_drafts.md](core_loop_roadmap_issue_drafts.md)

## T1 P0-M2 — Normalize execution mode/domain

1) Parameter validation hardening  
- Validate `execution_domain/mode`, remove deprecated modes.  
- Outputs: validation logic, standardized errors.

2) Default-safe downgrade logic  
- Downgrade to compute-only on ambiguous/missing inputs; add logs/metrics.  
- Outputs: downgrade handling, regression tests.

3) Docs/help cleanup  
- Remove legacy modes from CLI/SDK help and guides; document the canonical rules.  
- Outputs: updated docs/help text.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md)

## T2 P0-M1 — Unify evaluation/activation

1) Enforce WS as SSOT  
- Expose only WS results in Runner/CLI/API; separate ValidationPipeline outputs as pre-checks.  
- Outputs: direct WS result paths, isolated pre-check section.

2) Schema sharing  
- Publish WS API schema as a shared module; remove duplicate types.  
- Outputs: schema module, compatibility tests.

3) Ops/dev guide refresh  
- Document activation/contribution interpretation and where ValidationPipeline sits.  
- Outputs: updated ops/dev guides.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [worldservice.md](../architecture/worldservice.md)

## T2 P0-M2 — ExecutionDomain rule alignment

1) WS input validation hardening  
- Downgrade to compute-only on missing/ambiguous ExecutionDomain; standardize errors.  
- Outputs: stricter validation/messages, tests.

2) Remove Runner submission hints  
- Block domain hints in submission metadata; restate WS-priority rules.  
- Outputs: cleaned submission path, warnings/logs.

3) Tests/E2E  
- Add downgrade/reject contract tests; drop legacy modes from docs.  
- Outputs: test cases, updated docs.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [gateway.md](../architecture/gateway.md)

## T3 P0-M1 — World-based data presets

1) World preset spec  
- Define world/preset → data preset mapping with examples.  
- Outputs: spec section in `world/world.md`.

2) Runner/CLI auto-wiring  
- Implement preset-driven Seamless provisioning; demote direct `history_provider` setup.  
- Outputs: auto-wiring code, regression tests.

3) Examples/guides  
- Add runnable preset examples; update guides/tutorials.  
- Outputs: refreshed examples and docs.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md), [world.md](../world/world.md)

## T4 P0-M1 — Align ComputeContext/ExecutionDomain

1) Apply the canon rules  
- Enforce `compute_context.py` rules across Gateway/DM/SDK.  
- Outputs: refactored context construction.

2) Enforce WS decision priority  
- Standardize submission meta handling (incl. as_of/ComputeKey); emit errors/metrics on priority violations.  
- Outputs: validation logic, metrics/logs.

3) Contract tests  
- Add ComputeContext decision-path tests.  
- Outputs: test cases, CI wiring.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [dag-manager.md](../architecture/dag-manager.md)

## T4 P0-M2 — NodeID/TagQuery determinism

1) Document the rules  
- Define and share NodeID/TagQuery determinism rules.  
- Outputs: docs/comments, consolidated rules.

2) Apply per engine  
- Add determinism checks to DAG Manager/Gateway/SDK creation/expansion paths.  
- Outputs: validation logic, regression tests.

3) Observability/tests  
- Add determinism regression tests; alerts/logs/metrics on drift.  
- Outputs: tests/metrics, dashboard wiring.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [dag-manager.md](../architecture/dag-manager.md), [gateway.md](../architecture/gateway.md)

## T5 P0-M1 — Determinism checklist

1) Implement the checklist  
- Apply NodeID CRC, NodeCache GC, TagQuery stability, etc.  
- Outputs: hardened modules, unit tests.

2) Observability signals  
- Add determinism metrics/logs; wire to ops dashboards.  
- Outputs: metrics/alerts.

3) Runbook updates  
- Capture key failure/recovery flows.  
- Outputs: refreshed runbooks.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md)

## T6 P0-M1 — Core Loop contract test suite

1) Skeleton  
- Shape `tests/e2e/core_loop` flow and fixtures.  
- Outputs: test skeleton.

2) Core cases  
- Implement SubmitResult alignment, ExecutionDomain default-safe downgrade, TagQuery stability.  
- Outputs: test cases, xdist-friendly fixtures if needed.

3) CI integration/docs  
- State merge-blocking rule; document how to run the suite.  
- Outputs: CI wiring, docs.

Refs: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), `tests/e2e/core_loop`
