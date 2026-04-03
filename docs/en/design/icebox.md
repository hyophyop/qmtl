---
title: "Design Icebox Index"
tags: [design, icebox, docs]
author: "QMTL Team"
last_modified: 2026-04-04
---

# Design Icebox Index

This page is the entry point for reference-only drafts and sketches under `docs/en/design/icebox/`.

- Purpose: keep non-SSOT design material discoverable without exposing every draft in the public nav.
- Visibility: individual `icebox/*` pages stay off-nav by default; use this index as the front door.
- Normative status: none. Adopted material must be promoted into `docs/en/architecture/`, `docs/en/operations/`, code, or tests.

## Usage rules

- Confirm the current architecture docs and code before using an icebox page as implementation input.
- Treat drafts without a complete `ko`/`en` pair as locale-incomplete and keep them off-nav until both paths exist.
- Archive or delete stale drafts once their useful decisions have been promoted.

## Document groups

### World validation and risk

- [World validation architecture sketch](icebox/world_validation_architecture.md)
- [World validation v1 implementation plan](icebox/world_validation_v1_implementation_plan.md) - archived checklist
- [WorldService evaluation runs and metrics API](icebox/worldservice_evaluation_runs_and_metrics_api.md)
- [QMTL model risk management (MRM) framework sketch](icebox/model_risk_management_framework.md)
- [Exit Engine overview (draft)](icebox/exit_engine_overview.md)
- [World strategy weighting v1.5 design](icebox/world_strategy_weighting_v1.5_design.md)

### Strategy, UI, and configuration experiments

- [QMTL UI](icebox/qmtl_ui.md)
- [Strategy distillation](icebox/strategy_distillation.md)
- [YAML-only configuration overhaul](icebox/yaml_config_overhaul.md)
- [Seamless materialize/verify surface split design](icebox/seamless_materialize_jobs.md)

### Integration and spike notes

- [QMTL SR integration proposal](icebox/sr_integration_proposal.md)
- [SR-QMTL data consistency design sketch](icebox/sr_data_consistency_sketch.md)
- [Operon follow-up integration and pyoperon spike notes](icebox/operon_followup_spike.md)

{{ nav_links() }}
