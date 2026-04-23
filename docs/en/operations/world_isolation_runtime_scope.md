# World Isolation Runtime Scope

The remaining world-isolation gap is operational rather than architectural: align who is allowed to write with how local writable paths are scoped. This runbook does not redefine the core contracts; it captures the RBAC, write-scope, and namespace checks operators must verify in real deployments and backtest environments.

Related normative documents:

- [Architecture & World ID Flow](../architecture/architecture.md)
- [WorldService](../architecture/worldservice.md)
- [Configuration Reference](../reference/configuration.md)

## 1. Authority and write ownership

- WorldService remains the authority for world-scoped RBAC and write audit. `apply`, `activation PUT`, and world-state mutation stay behind WorldService operator permissions only.
- Gateway is a proxy/bridge, not the source of truth for write-scope. Local Gateway or SDK settings must not bypass the WorldService boundary.
- `live`/`shadow` must not be used as writable local cache/artifact domains. As defined by the existing contract, cross-domain reuse remains limited to read-only consumption of immutable feature artifacts.

## 2. Local storage policy for backtest/dryrun

- Any local writable path used by `backtest`/`dryrun` must be namespaced by both `world_id` and `execution_domain`.
- When the runtime uses default or relative paths, it must avoid reusing long-lived shared directories and instead route writes under the ephemeral root (`$TMPDIR/qmtl/...`).
- When operators provide an explicit absolute path, the effective write target must still be separated under `world=<id>/execution_domain=<domain>`.
- This policy applies to:
  - `seamless.artifact_dir`
  - `cache.feature_artifact_dir`
  - `cache.tagquery_cache_path`

## 3. Queue / cache / artifact namespace checklist

- Queue topics: production topics must stay in the `{world_id}.{execution_domain}.<topic>` form.
  - Regression guard: `tests/qmtl/services/dagmanager/test_topic_namespace.py`
- Feature artifact write-scope: keep `cache.feature_artifact_write_domains` restricted to `backtest`/`dryrun`, while `live`/`shadow` remain read-only consumers.
  - Regression guard: `tests/qmtl/runtime/sdk/test_feature_artifact_plane.py`
- TagQuery local cache: in backtest/dry-run, use world/domain-scoped paths and push default/relative locations into the ephemeral root.
  - Regression guard: `tests/qmtl/runtime/sdk/tagquery/test_cache_parity.py`
- Seamless artifact manifests: producer provenance must retain `world_id`, `execution_domain`, and `strategy_id`.
  - Regression guard: `tests/qmtl/runtime/sdk/test_artifact_registrar.py`

## 4. Minimum pre-approval audit

- Confirm world write APIs exist only behind the WorldService RBAC boundary.
- Confirm local backtest/dry-run runs write cache/artifact data under `world=<id>/execution_domain=<domain>`.
- When operations rely on relative paths or home-directory defaults, confirm the actual write target is downgraded into the ephemeral root.
- Run the queue-namespace, feature-artifact write-domain, and manifest-provenance regression tests together before approval.
