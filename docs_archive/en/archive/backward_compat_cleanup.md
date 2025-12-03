# Backward Compatibility Cleanup Notes

## Purpose
- Temporary scratchpad to track backward-compat/legacy surfaces, prioritize removals, and flag risky areas.

## Quick Inventory
- Search counts: `rg -l "backward|legacy" qmtl | wc -l` → 31 files; `rg -l "deprecated" qmtl | wc -l` → 6 files.
- CLI wrappers/options: legacy entrypoint shims in `qmtl/interfaces/cli/add_layer.py`, `list_layers.py`, `validate.py`, `layer.py`; legacy template/option warnings in `interfaces/cli/init.py`; legacy template toggle in `interfaces/cli/presets.py`; related strings in `locale/ko/LC_MESSAGES/qmtl.po`.
- DAG Manager/Gateway compatibility: legacy subcommand/`--target` rewrite in `services/dagmanager/cli.py`; version-less DAG defaults in `services/dagmanager/schema_validator.py`; legacy API exception path in `services/dagmanager/server.py`; world_id/multi-world compatibility notes in `services/gateway/models.py`.
- Runtime SDK shims/aliases: history service proxies in `runtime/sdk/runner.py`; legacy volatility check in `runtime/sdk/risk_management.py`; `fill_missing` compatibility in `runtime/sdk/data_io.py`; accessor shim in `runtime/sdk/configuration.py`; deprecated options in `runtime/sdk/cli.py`; `runtime/brokerage/order.py` `cash()` alias.
- Seamless/Artifacts legacy paths: legacy fingerprint helper/export in `runtime/sdk/artifacts/fingerprint.py`; alias in `runtime/sdk/artifacts/registrar.py`; legacy kwargs/attrs preserved in `runtime/io/seamless_provider.py`; legacy fingerprint mode and `legacy_metadata` flows across `runtime/sdk/seamless_data_provider.py`; legacy re-export in `runtime/transforms/equity_linearity.py`.
- WorldService/storage/recipes/config compatibility: legacy Storage API emulation and test helper in `services/worldservice/storage/facade.py`; legacy bucket normalization in `services/worldservice/storage/nodes.py`; empty proxy in `.../persistent.py`; sentinel in `.../edge_overrides.py`; legacy component resolve/passthrough in `runtime/nodesets/recipes.py`; compatibility stubs in `runtime/nodesets/stubs.py`; `_backfill_legacy_worldservice` in `foundation/config.py`; attr alias in `foundation/common/metrics_factory.py`; legacy input handling in `foundation/common/tagquery.py` and `node_validation.py`; legacy notes in examples `examples/templates/local_stack.example.yml`, `examples/strategies/dryrun_live_switch_strategy.py`, `examples/worldservice/gating_policy.example.yml`.

## Low-Risk Removal Candidates
- (Done) Removed CLI legacy entrypoints that only delegated (`interfaces/cli/add_layer.py`, `list_layers.py`, `validate.py`, wrapper functions in `layer.py`) and related translations/options (`presets.py`, `init.py`).
- Legacy guidance text in examples/templates (e.g., `examples/templates/local_stack.example.yml`) that can move to a migration note if still needed.

## Areas Requiring Usage Verification
- Extensive legacy fingerprint/`legacy_metadata` flows in `runtime/sdk/seamless_data_provider.py`: confirm external consumers before removal.
- Legacy Storage API emulation in `services/worldservice/storage/facade.py` and `.../nodes.py`: verify test/operational callers.
- SDK-facing shims in `runtime/sdk/runner.py`, `runtime/sdk/data_io.py`, `runtime/sdk/risk_management.py`: check public usage before cutting.
- DAG manager CLI rewrite (`services/dagmanager/cli.py`) and schema v1 fallback: confirm deployment/CI consumers.
- Config backfill (`foundation/config.py`), metric attr alias (`foundation/common/metrics_factory.py`), tag/node validation legacy inputs: ensure data is normalized first.

## Next Actions (draft)
- Usage discovery: grep/call-graph internal consumers; for public CLI/SDK surfaces, prep release notes and deprecation comms.
- Removal sequencing: low-risk CLI/examples → internal-only shims → public SDK surface → service-layer fallbacks.
- Pre/post checks: align or prune related tests, run `uv run -m pytest -W error -n auto`, and scrub legacy mentions in docs/mkdocs alongside code changes.

## Progress Log
- Removed project CLI legacy aliases and deprecated flags (`--strategy`, `--show-legacy-templates`, `--list-*`) and refreshed docs/translations/tests accordingly.
- Dropped dagmanager CLI legacy `--target` rewrites; only canonical argument order is supported now, tests updated.
- Removed Runner history-service compatibility proxies; Runner now calls the service directly, and tests reference the non-legacy helpers.
- Config layer tightened: removed gateway/dagmanager DSN aliases (`*_url`/`*_uri`) and worldservice backfill; loader now only accepts canonical keys.
- SDK config helpers: dropped `get_unified_config`/`reload` shims; runtime flag loader now relies on canonical config plus defaults.
- DAG schema: made `schema_version` mandatory (no default v1 fallback) and updated tests to send explicit versions in DAG payloads.
- WorldService: removed legacy world-node bucket normalization and storage facade legacy proxies; tests now rely on canonical repositories/structures.
- Seamless: dropped legacy fingerprint/metadata paths and canonicalised fingerprint mode.
- HistoryProvider: removed the default `ensure_range`→`fill_missing` proxy; Seamless provider now implements `ensure_range` explicitly.
- NodeSet recipes: removed the legacy component resolver/**kwargs path; only explicit step overrides are allowed, tests updated.
- Equity linearity: removed the legacy re-export wrapper tests (metrics module remains the public surface).
- Seamless provider: dropped `cache_provider`/`storage_provider` attribute fallbacks on data source wrappers.
- Artifact registrar: removed `FileSystemArtifactRegistrar.from_env` alias; presets use the canonical factory only.
- TagQuery: reject non-dict queue descriptors and missing `queue` keys instead of silently skipping legacy shapes.
- Brokerage: removed the single-currency `cash` compatibility property; consumers/tests now use the cashbook directly.
- Docs: removed legacy flags/notes from template reference and deleted CCXT Seamless legacy audit docs (nav/inventory/links cleaned).

## Remaining cleanup candidates (reminder list)
- Nodesets: compatibility stubs in `runtime/nodesets/stubs.py` (review whether to keep).
- Metrics/tag/node: attr alias in `foundation/common/metrics_factory.py`; legacy input handling in `foundation/common/tagquery.py` and `node_validation.py`.
- Gateway/Dagmanager: world_ids/world_id compat branches in `services/gateway/models.py` and legacy excepts in `services/gateway/server.py` / `services/dagmanager/server.py`.
- Docs/examples: legacy option/env/topic/node ID mentions (layered_templates_quickstart migration section, `docs/en/guides/ccxt_seamless_usage.md` legacy env, `docs/en|ko/operations/neo4j_migrations.md`/`backfill.md` legacy notes, `docs/en/reference/api_world.md`/`architecture/worldservice.md`/`gateway.md` legacy fields, `examples/templates/local_stack.example.yml` legacy topic note, `examples/strategies/dryrun_live_switch_strategy.py` docstring, etc.).
- Misc tests/comments: e.g., legacy mentions in `services/gateway/tests/test_nodeid.py` used for rejection scenarios (review as needed).
