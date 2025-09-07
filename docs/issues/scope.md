# QMTL Issue Scope

The following issues are tracked for automated Codex runs. Each entry includes a concrete scope with acceptance criteria and target paths limited to `qmtl/` and project docs.

- ID: 761
  Title: Docs — Sync Neo4j schema section with implemented indexes and idempotency
  Summary: The code in `qmtl/dagmanager/neo4j_init.py` applies additional indexes (`compute_tags`, `queue_interval`, `compute_buffering_since`) that are not reflected in `docs/architecture/dag-manager.md` §1.2. Bring the documentation in sync and note that all DDL uses `IF NOT EXISTS` for idempotency. Include a short usage note for `qmtl dagmanager neo4j-init` and `export-schema`.
  Acceptance:
    - Section §1.2 lists all currently applied constraints/indexes, including: `compute_pk`, `kafka_topic`, `compute_tags`, `queue_interval`, `compute_buffering_since`.
    - A brief note explains idempotency (`IF NOT EXISTS`) and links the relevant CLI.
    - `uv run mkdocs build` succeeds with no new warnings/errors.
  Affected:
    - docs/architecture/dag-manager.md

- ID: 762
  Title: DAG Manager — Add safe Neo4j schema rollback (CLI + helpers)
  Summary: Provide a safe rollback path to drop the constraints/indexes created by `neo4j-init`. Add helpers in `neo4j_init.py` to generate and apply `DROP ... IF EXISTS` statements, and expose a `qmtl dagmanager neo4j-rollback` CLI subcommand.
  Acceptance:
    - `qmtl/dagmanager/neo4j_init.py` exposes `get_drop_queries()` and `rollback_schema(driver)` (and a convenience `rollback(uri, user, password)` or reuse connect()) that drop only the items created by init.
    - `qmtl/dagmanager/cli.py` adds a `neo4j-rollback` subcommand with `--uri/--user/--password`.
    - A small unit test asserts that `get_drop_queries()` includes the expected `DROP` statements for all created objects (no Neo4j dependency).
    - Docs: Add a short section to `docs/architecture/dag-manager.md` or a small ops page referencing rollback usage. MkDocs still builds.
    - Preflight tests pass: `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q -k 'not slow' --timeout=60 --timeout-method=thread --maxfail=1`.
  Affected:
    - qmtl/dagmanager/neo4j_init.py
    - qmtl/dagmanager/cli.py
    - tests/test_neo4j_schema_rollback.py
    - docs/architecture/dag-manager.md (or docs/operations/neo4j_migrations.md)

- ID: 763
  Title: Gateway — Ensure /strategies/dry-run always returns a non-empty sentinel_id
  Summary: The dry-run endpoint falls back to TagQuery when Diff is not available. In that fallback, `sentinel_id` may be empty. Derive a deterministic non-empty value (e.g., `dryrun:<crc32_of_node_ids>`) when Diff is unavailable, preserving existing behavior when Diff succeeds. Document the parity rule briefly in README.
  Acceptance:
    - Update `qmtl/gateway/routes.py` dry-run handler to set a deterministic `sentinel_id` when Diff is unavailable (no external dependencies; keep current shapes and TagQuery behavior intact).
    - Add a lightweight unit test that exercises the helper used to derive the fallback sentinel id (pure function; does not boot FastAPI), or validates the code path by calling the function on a small DAG stub.
    - Update `README.md` (TagQuery/Dry-run section) to mention sentinel_id parity and fallback rule.
    - Preflight tests pass and MkDocs build succeeds.
  Affected:
    - qmtl/gateway/routes.py
    - tests/test_gateway_dryrun.py
    - README.md
