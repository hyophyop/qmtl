# YAML-Only Configuration Overhaul

!!! warning "Icebox (Reference-only)"
    This document lives under `docs/en/design/icebox/` and is **not an active work item/SSOT**. Use it for background/reference only; promote adopted parts into `docs/en/architecture/` or code/tests.

## Overview
This document captures the implementation roadmap for moving every QMTL component to a single YAML-based configuration source. It is scoped to the work tracked in [Issue #1337](https://github.com/hyophyop/qmtl/issues/1337) and establishes the guardrails that downstream workstreams must follow.

## Goals
- Eliminate environment-variable based configuration reads across services, SDK tooling, Seamless runtime, and examples.
- Provide a canonical schema with validation that is shared by all components.
- Ensure the full stack (local development, CI, and production) boots exclusively from YAML definitions.

## Non-Goals
- Introducing new configuration keys unrelated to the consolidation effort.
- Refactoring runtime feature flags that are unrelated to configuration bootstrapping.
- Modifying vendor SDKs where configuration is delegated externally.

## Workstreams
The epic is decomposed into nine focused workstreams. Each workstream must align with the conventions defined here and produce unit/integration coverage for its surface area.

| Workstream | Description | Key Deliverables | Acceptance Signals |
| --- | --- | --- | --- |
| #1338 Unified YAML schema | Author a `qmtl/config/schema.yaml` that defines every configuration stanza, alongside dataclass bindings and docs. | Schema file, loader models, schema docs. | Schema round-trips with loader examples; docs updated. |
| #1339 Config loader & CLI | Replace scattered loaders with a consolidated `qmtl.config` package and extend `qmtl config validate`. | Loader module, CLI rewrite, test suite. | CLI fails fast on invalid docs; loader is the single import path. |
| #1340 WorldService migration | Move WorldService bootstrap to the loader and remove env reads. | Service wiring changes, system tests. | Service boots with YAML only. |
| #1341 Gateway & DAG Manager migration | Same as above for Gateway and DAG Manager. | Service config adaptors, HTTP/WebSocket test coverage. | Gateway & DAG Manager rely solely on loaded config. |
| #1342 Seamless runtime migration | Port Seamless runtime configuration to YAML, including snapshots and caching knobs. | YAML ingestion layer, runtime tests. | Seamless runtime starts without env defaults. |
| #1343 SDK/connectors/caching migration | Update SDK CLI, connectors, and caches to read YAML. | CLI updates, connector adapters, caches. | CLI help references YAML; env reads removed. |
| #1344 Docs rewrite | Update docs, guides, and templates to reference the YAML config. | Docs, nav updates, examples. | No docs mention env vars for config. |
| #1345 Ops templates update | Refresh stack templates under `docs/templates/` and operational playbooks. | Template files, validation steps. | Ops runbooks show YAML injection workflows. |
| #1346 Test/validation suite | Extend automated validation for YAML compliance across components. | Test harness updates, CI wiring. | Preflight checks ensure YAML-only boot. |

## Cross-Cutting Requirements
- **Configuration Package**: All new loaders should live under a top-level `qmtl/config/` namespace with clear separation between schema, validation, and IO helpers.
- **Environment Variable Sunset**: Identify each `os.getenv` occurrence and either delete it or replace it with a compatibility shim that reads from the YAML loader. Shims should emit warnings and be tracked for removal once downstream work is complete.
- **Secrets Management**: The YAML format must support references to secret backends (e.g., SOPS, Vault). Standardize on documenting the reference syntax, but defer backend integration to follow-up issues if necessary.
- **Backward Compatibility**: Provide a transition period through deprecation warnings surfaced in CLI output and logs. Each workstream should state how users migrate their configuration prior to removing env support.
- **Validation Levels**: Establish `strict` and `permissive` validation modes to support incremental adoption during rollout. Strict mode becomes the default once the migration completes.

## Migration Plan
1. **Schema Foundation (Weeks 1-2)**
   - Finalize configuration taxonomy and produce the canonical schema file.
   - Add fixtures for sample environments (local, staging, production) in `examples/config/`.
2. **Loader & CLI (Weeks 2-3)**
   - Introduce loader package and migrate CLI validation commands.
   - Implement schema-driven help output.
3. **Service Rollout (Weeks 3-5)**
   - Migrate WorldService, Gateway, DAG Manager, and Seamless runtime sequentially.
   - Provide feature flags to opt-in via YAML during the transition.
4. **SDK & Connectors (Weeks 4-6)**
   - Update SDK, connectors, and caches to consume the loader output.
   - Offer adapter utilities for community connectors.
5. **Docs & Templates (Weeks 5-6)**
   - Rewrite guides, operations docs, and templates to use the YAML workflow.
   - Archive environment variable guidance with deprecation notes.
6. **Validation & Cleanup (Weeks 6-7)**
   - Expand unit/integration suites.
   - Remove deprecated env paths and finalize strict validation.

## Testing Strategy
- Add schema snapshot tests that assert compatibility between YAML examples and the loader output.
- Ensure every service exposes a `--config` flag that points to the canonical YAML file and fails when absent.
- Introduce integration tests under `tests/config/` that spin up minimal instances using the YAML loader.
- Run the existing `uv run -m pytest -W error -n auto` suite with env variables removed to catch regressions.

## Operational Considerations
- **Deployment Tooling**: Update deployment scripts (Helm, Terraform, Compose) to mount YAML config maps/secrets instead of injecting env vars.
- **Secrets Rotation**: Provide guidance for rotating secrets stored in YAML via encrypted values.
- **Observability**: Emit structured logs during startup that confirm the active YAML file and validation mode.

## Next Steps
- Kick off #1338 and #1339 in parallel with shared schema ownership.
- Draft communication plan for users about the deprecation timeline.
- Evaluate whether config diffs should be surfaced in ControlBus events.

## References
- [Issue #1337](https://github.com/hyophyop/qmtl/issues/1337) – Epic tracker.
- [Operations Config CLI](../../operations/config-cli.md) – Existing CLI usage that will be updated.
