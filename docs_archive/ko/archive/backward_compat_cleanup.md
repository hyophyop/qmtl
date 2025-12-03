# 하위호환 제거 작업 메모

## 목적
- 하위호환·레거시 코드 제거 범위를 정리하고, 삭제 우선순위와 주의 지점을 공유하기 위한 임시 기록.

## 빠른 인벤토리
- 검색 결과: `rg -l "backward|legacy" qmtl | wc -l` → 31개 파일, `rg -l "deprecated" qmtl | wc -l` → 6개 파일.
- CLI 호환 래퍼/옵션: `qmtl/interfaces/cli/add_layer.py`, `list_layers.py`, `validate.py`, `layer.py`의 legacy 엔트리포인트 위임, `interfaces/cli/init.py`의 legacy 템플릿/옵션 경고, `interfaces/cli/presets.py`의 legacy 템플릿 표시 옵션, 관련 문자열은 `locale/ko/LC_MESSAGES/qmtl.po`에 반영.
- DAG Manager/Gateway 호환 처리: `services/dagmanager/cli.py`의 legacy subcommand/`--target` 재작성, `services/dagmanager/schema_validator.py`의 버전 없는 DAG v1 처리, `services/dagmanager/server.py`의 legacy API 예외 경로, `services/gateway/models.py`의 world_id/multi-world 호환 주석.
- Runtime SDK 호환 프록시/별칭: `runtime/sdk/runner.py`의 history service 프록시 메서드, `runtime/sdk/risk_management.py` 구식 변동성 체크, `runtime/sdk/data_io.py`의 `fill_missing` 호환, `runtime/sdk/configuration.py` accessor shim, `runtime/sdk/cli.py`의 deprecated 옵션, `runtime/brokerage/order.py`의 `cash()` 별칭.
- Seamless·Artifacts 레거시 경로: `runtime/sdk/artifacts/fingerprint.py`의 legacy fingerprint 헬퍼와 export, `runtime/sdk/artifacts/registrar.py` alias, `runtime/io/seamless_provider.py`의 legacy kwargs/속성 보존, `runtime/sdk/seamless_data_provider.py`의 legacy fingerprint 모드·`legacy_metadata` 경로, `runtime/transforms/equity_linearity.py`의 구 API 재수출.
- WorldService/스토리지·레시피/설정 호환: `services/worldservice/storage/facade.py`의 legacy Storage API 에뮬레이션과 테스트 헬퍼, `services/worldservice/storage/nodes.py`의 legacy 버킷 정규화, `.../persistent.py`의 빈 proxy, `.../edge_overrides.py` sentinel; `runtime/nodesets/recipes.py` legacy component resolve/passthrough, `runtime/nodesets/stubs.py` 호환 스텁; `foundation/config.py`의 `_backfill_legacy_worldservice`, `foundation/common/metrics_factory.py` attr alias, `foundation/common/tagquery.py`·`node_validation.py`의 legacy 입력 처리, 예제 `examples/templates/local_stack.example.yml`, `examples/strategies/dryrun_live_switch_strategy.py`, `examples/worldservice/gating_policy.example.yml`에도 legacy 안내가 존재.

## 단기 제거 후보 (낮은 위험)
- (완료) 단순 위임만 하는 CLI legacy 엔트리포인트(`interfaces/cli/add_layer.py`, `list_layers.py`, `validate.py`, `layer.py` 내부 wrapper) 제거 및 대응 번역/옵션(`presets.py`, `init.py`) 정리.
- 예제/템플릿의 legacy 안내 문구 정리(`examples/templates/local_stack.example.yml` 등) 후 필요 시 마이그레이션 가이드로 이동.

## 진행 상황 메모
- 프로젝트 CLI에서 legacy alias와 `--strategy`/`--show-legacy-templates`/`--list-*` 폐기 옵션 제거, 문서·번역·테스트 업데이트 완료.
- DAG Manager CLI의 legacy `--target` 재작성 제거(표준 인자 순서만 지원), 대응 테스트 업데이트.
- Runner의 History 서비스 호환 프록시 제거(직접 서비스 호출로 단순화), 관련 테스트 정리.
- 설정 계층: gateway/dagmanager DSN alias(`*_url`/`*_uri`)와 worldservice 백필 제거, config 로더가 캐노니컬 키만 수용하도록 변경.
- SDK 설정 헬퍼: `get_unified_config`/`reload` 호환 accessor 제거, 런타임 플래그 로더가 캐노니컬 설정과 기본값만 사용.
- DAG 스키마: schema_version 필수화 및 v1 기본값 제거, 관련 테스트의 DAG payload에 명시적 버전 추가.
- WorldService: 레거시 노드 버킷 정규화와 스토리지 facade의 호환용 프록시 제거, 테스트는 캐노니컬 구조 사용.
- Seamless: legacy fingerprint/metadata 경로 제거, fingerprint 모드 canonical로 고정.
- HistoryProvider: `ensure_range`의 fill_missing 프록시 기본값 제거(명시적 구현 필요), Seamless provider에 명시적 구현 추가.
- NodeSet 레시피: legacy component resolver/**kwargs 경로 제거, step override만 허용하도록 단순화, 테스트 갱신.
- Equity linearity: 구 re-export/wrapper 테스트 제거(메트릭 모듈만 노출).
- Seamless provider: data source wrapper의 legacy `cache_provider`/`storage_provider` 속성 fallback 제거.
- Artifact registrar: `FileSystemArtifactRegistrar.from_env` 호환 alias 삭제, preset이 캐노니컬 팩토리만 사용.
- TagQuery: queue descriptor가 dict 형태가 아니거나 `queue` 키가 없으면 오류로 간주(legacy 문자열 스킵 제거).
- Brokerage: Account의 단일 통화 `cash` 호환 프로퍼티 제거, 소비자와 테스트를 cashbook 기반으로 정리.
- 문서: 템플릿 문서에서 legacy 플래그/자료 언급 제거, CCXT Seamless legacy 감사 문서 삭제 및 nav/inventory/참조 링크 정리.

## 남은 삭제/정리 후보 (추가 메모)
- Nodesets: `runtime/nodesets/stubs.py` 호환 스텁 정리 여부 검토.
- Metrics/validation: `foundation/common/metrics_factory.py` attr alias, `foundation/common/tagquery.py`·`node_validation.py` legacy 입력 처리.
- Gateway/Dagmanager: `services/gateway/models.py` world_ids/world_id 호환 브랜치 및 `server.py` legacy except, `services/dagmanager/server.py` legacy except.
- 문서/예제: legacy 옵션/환경변수/토픽/노드ID 언급 정리(layered_templates_quickstart migration 섹션, `docs/en/guides/ccxt_seamless_usage.md` legacy env, `docs/en|ko/operations/neo4j_migrations.md`·`backfill.md` legacy 언급, `docs/en/reference/api_world.md`/`architecture/worldservice.md`/`gateway.md` legacy 필드, `examples/templates/local_stack.example.yml` legacy topic 안내, `examples/strategies/dryrun_live_switch_strategy.py` docstring 등).
- 기타 테스트/주석: `services/gateway/tests/test_nodeid.py` 등에서 등장하는 “legacy”는 맥락 확인 후 필요 시 정리.
## 주의가 필요한 영역 (사용처 검증 필요)
- `runtime/sdk/seamless_data_provider.py` 전반의 legacy fingerprint/`legacy_metadata` 경로: 외부 소비자 여부 확인 후 단계적 제거 필요.
- `services/worldservice/storage/facade.py` 및 `.../nodes.py`의 legacy API 에뮬레이션: 테스트/운영 호출 여부 확인 필수.
- `runtime/sdk/runner.py`의 history 프록시, `runtime/sdk/data_io.py`·`risk_management.py` 구식 경로: 공개 SDK 표면에 노출된 사용처 조사 필요.
- DAG manager CLI 인자 재작성(`services/dagmanager/cli.py`)과 schema validator의 v1 fallback: 운영 배포와 CI 사용처 확인 후 제거 검토.
- 설정 백필(`foundation/config.py`), metric attr alias(`foundation/common/metrics_factory.py`), tag/node validation의 legacy 입력 허용: 설정/노드 데이터가 이미 정규화됐는지 확인 필요.

## 다음 액션 초안
- 사용 현황 파악: `git grep`/call graph로 내부 사용 여부를 먼저 확인하고, 외부 노출된 CLI/SDK 표면은 릴리스 노트나 deprecation 안내 준비.
- 제거 순서 합의: 위험 낮은 CLI/예제 → 내부 only shim → SDK 공개 표면 → 서비스 레이어 fallback 순으로 진행 제안.
- 제거 전후 체크: 관련 테스트 케이스 파악 및 정리, `uv run -m pytest -W error -n auto`로 회귀 검증, docs/mkdocs 내 legacy 언급 동시 정리.
