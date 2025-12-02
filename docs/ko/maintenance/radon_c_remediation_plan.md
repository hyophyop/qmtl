# Radon C 등급 정리 임시 계획

## 최신 스냅샷 (2025-12-02)
- 측정 명령: `uv run --with radon -m radon cc -s -n C qmtl`
- 영역별 C 등급 함수/메서드:
  - 테스트/보조만 남음: 게이트웨이 테스트 헬퍼 `tests/test_strategy_submission_helper.assert_submission_result`, `tests/test_api_background.test_start_and_stop_background_lifecycle`, 예제 테스트 `examples/tests/test_brokerage_e2e.py::test_brokerage_e2e_scenarios`.

## 우선순위 및 배치
1) 런타임 SDK 핵심(검증/캐시/백필/타이밍)  
   - 완료: `ValidationPipeline.validate`, `risk_management._apply_override_values`, 캐시/백필 경로(`_build_frame`, `backfill_bulk`, `_build_log_extra`, `CacheView.__getitem__`, `NodeFeedMixin.feed`, `MarketHours`, `HistoryWarmupPoller.poll`, `LiveReplayBackfillStrategy.ensure_range/_collect_events`, `FeatureArtifactPlane.from_env`).  
   - 캐시/백필 관련 신규 C 발생 시 즉시 diff-scan.
2) 게이트웨이 라우팅/입력 파서  
   - 완료: `_parse_kafka_message`, `_resolve_world_modes`, `_resolve_time_in_force`, `OwnershipManager.acquire`.  
   - 남은 테스트 보조 함수는 게이트웨이 배치에서 후속 정리.
3) 테스트/보조 정리  
   - 게이트웨이 테스트 헬퍼와 예제 테스트의 복잡도/지선택 refactor 또는 파라미터화로 낮추기. 필요 시 `-k` 제외 대신 구조 단순화.

## 공통 리팩터 지침
- 가드 절과 테이블 기반 분기로 if/elif 체인 축소, 불변 데이터 구조 사용.
- I/O와 계산 분리: 데이터 준비/검증 → 핵심 계산 → 출력/로그 단계로 나누기.
- 반복 포맷/변환 로직은 작은 헬퍼로 추출해 공유하고, 계약(딕트 키/타입)을 명시.
- 작은 단위 테스트로 추출 헬퍼의 계약을 고정해 회귀 방지.
- 변경 시 radon diff(`git diff --name-only origin/main... | rg '\.py$' | xargs -r uv run --with radon -m radon cc -s -n C`)와 CI 전체(아래 검증 루틴)를 함께 실행.

## 검증 루틴
- 순서: `uv run --with mypy -m mypy` → `uv run mkdocs build --strict` → `uv run python scripts/check_design_drift.py` → `uv run python scripts/lint_dsn_keys.py` → `uv run --with grimp python scripts/check_import_cycles.py --baseline scripts/import_cycles_baseline.json` → `uv run --with grimp python scripts/check_sdk_layers.py` → `uv run python scripts/check_docs_links.py` → `uv run -m pytest --collect-only -q` → `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1 -k 'not slow'` → `PYTHONPATH=qmtl/proto uv run pytest -p no:unraisableexception -W error -q tests` → `USE_INPROC_WS_STACK=1 WS_MODE=service uv run -m pytest -q tests/e2e/world_smoke -q`.
- C로 남은 함수는 리팩터 전/후 radon 점수와 주요 테스트 결과를 PR 본문에 기록.

## 진행/기록
- 완료된 C 정리: `order_types`, `execution_diffusion_contraction`, `nodesets.resources`, `risk_management._apply_override_values`, `ValidationPipeline.validate`, `cache_view_tools._build_frame`, `arrow_cache.backend.NodeCacheArrow.backfill_bulk`, `backfill_coordinator._build_log_extra`, `cache_view.CacheView.__getitem__`, `nodes.mixins.NodeFeedMixin.feed`, `timing_controls.MarketHours`, `HistoryWarmupPoller.poll`, `LiveReplayBackfillStrategy.ensure_range/_collect_events`, `FeatureArtifactPlane.from_env`, `controlbus_consumer._parse_kafka_message`, `routes.rebalancing._resolve_world_modes`, `rebalancing_executor._resolve_time_in_force`, `ownership.OwnershipManager.acquire`, `queue_updates.publish_queue_updates`, `queue_store._extract_tag/_coerce_timestamp`, `garbage_collector.GarbageCollector.collect`, `node_repository.MemoryNodeRepository.get_buffering_nodes`, `interfaces.tools.taglint.validate_tags/write_tags`, `interfaces.cli.config._execute_validate`, `metrics_factory._get_or_create_metric`, `categorize_exception`, `_try_load_po`, SR 파서 경로(`_parse_points`, `build_strategy_from_dag_spec`, `_normalize_expr`, `_DagBuilder.walk/_maybe_division`, `_remove_identities`).  
- 남은 C(2025-12-02 기준): 최신 스냅샷 목록 참조. 작업별 radon 전/후 수치를 커밋 메시지 또는 PR 본문에 남길 것.
