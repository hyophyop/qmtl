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

- ID: 764
  Title: Backfill/IO — HistoryProvider 주입·불변(immutability) 보장 테스트/가이드
  Summary: `StreamInput`의 `history_provider`/`event_recorder`는 생성 시점 주입 및 불변이어야 합니다. 불변성 위반 테스트를 추가하고, EventRecorderService 경로가 QuestDB 데모와 일치하는지 확인합니다.
  Acceptance:
    - 재할당 시 `AttributeError` 발생을 검증하는 단위 테스트 추가.
    - EventRecorderService가 `bind_stream`을 통해 `recorder.table == stream.node_id`가 되도록 동작하는 테스트 추가.
    - MkDocs 빌드 및 테스트 프리플라이트 통과.
  Affected:
    - tests/test_streaminput_immutability.py
    - (참고) qmtl/sdk/node.py, qmtl/sdk/event_service.py, qmtl/io/eventrecorder.py

- ID: 765
  Title: CLI — 서브커맨드 --help·사용성 정비(qmtl gw|dagmanager|sdk)
  Summary: `qmtl <cmd> --help`가 실제 하위 CLI 도움말을 출력하도록 상위 디스패처를 수정하고, README 예시와 1:1로 일치하는지 검증 테스트를 추가합니다.
  Acceptance:
    - `qmtl dagmanager --help`에 `diff`, `export-schema`, `neo4j-init`, `neo4j-rollback`가 표시됨.
    - `qmtl gw --help`에 `--config`, `--no-sentinel`, `--allow-live`가 표시됨.
    - `qmtl sdk --help`에 `run`, `offline` 서브커맨드가 표시됨.
    - 위 항목을 검증하는 단위 테스트 추가 및 통과.
  Affected:
    - qmtl/cli/__init__.py
    - tests/test_cli_help.py

- ID: 766
  Title: Examples/Docs — 예제·튜토리얼 WS-first/중앙 태그/입력 시그니처 정렬
  Summary: 튜토리얼과 예제가 WS-first 실행 흐름, 중앙 `TagQueryManager` 처리, `ProcessingNode(input=...)` 시그니처로 일관되도록 확인/정비합니다.
  Acceptance:
    - 예제 코드에 `TagQueryNode.resolve()` 직접 호출 없음 (Runner가 처리).
    - `ProcessingNode(input=...)` 형태 사용(딕셔너리 입력 없음).
    - MkDocs 빌드 통과.
  Affected:
    - docs/guides/sdk_tutorial.md (설명 점검)
    - qmtl/examples/* (코드 점검)

- ID: 767
  Title: CI — 설계-코드 드리프트 감시(Design Drift Check)
  Summary: `docs/architecture/*`의 front-matter `spec_version`과 코드의 `ARCH_SPEC_VERSIONS`를 비교하는 스크립트를 추가하고, CI에 경고→실패 정책으로 연동합니다.
  Acceptance:
    - `scripts/check_design_drift.py`가 mismatch를 탐지하고 non-zero 종료.
    - `docs/architecture/gateway.md`, `docs/architecture/dag-manager.md` front-matter에 `spec_version` 추가.
    - `qmtl/spec.py`에 버전 맵 정의. CI에서 스텝 통과/실패 동작 확인.
  Affected:
    - scripts/check_design_drift.py
    - qmtl/spec.py
    - docs/architecture/gateway.md
    - docs/architecture/dag-manager.md
    - .github/workflows/ci.yml
