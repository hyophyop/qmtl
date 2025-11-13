---
title: "WS↔Gateway↔SDK 리밸런싱 스키마 조율 체크리스트"
tags: ["coordination", "rebalancing"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# WS↔Gateway↔SDK 리밸런싱 스키마 조율 체크리스트

이 문서는 Issue #1514 “Coordination: WS↔Gateway schema + SDK alpha metrics” 를 해소하기 위한 단일 체크리스트입니다. WorldService(#1513), Gateway/DAG(#1512), SDK Runtime(#1511)에서 동시에 작업할 항목을 모아 병렬 PR 병합 전에 확인하도록 설계했습니다.

## 배경

- MultiWorldRebalanceRequest/Plan 스키마는 기존 v1(스케일링 모드 전용)에서 v2(overlay/hybrid 대비, `alpha_metrics` 동봉)로 확장됩니다.
- `alpha_performance` 메트릭 키/단위를 SDK ↔ Gateway ↔ WorldService에서 일관되게 처리해야 합니다.
- 게이트/플래그/문서가 비동기적으로 합입되면 WS 응답을 Gateway가 파싱하지 못하거나 SDK가 새 지표를 오해할 수 있습니다.

## 진행 현황 (2025-11-13)

- **#1513 – WorldService:** `schema_version` 협상, `alpha_metrics` 봉투, v2 한정 `rebalance_intent.meta` 에코와 ControlBus `rebalancing_planned` 이벤트가 모두 동기화되었고 v1/v2 양쪽 계약 테스트를 추가했습니다 (`qmtl/services/worldservice/schemas.py#L248-L281`, `qmtl/services/worldservice/routers/rebalancing.py#L55-L219`, `qmtl/services/worldservice/controlbus_producer.py#L23-L109`, `tests/qmtl/services/worldservice/test_worldservice_api.py#L322-L480`).
- **#1512 – Gateway/DAG:** 설정·헬스 노출 외에 `WorldServiceClient.post_rebalance_plan`이 구성값 기준으로 v2를 선호하고 400/422 시 v1로 폴백하며, `/rebalancing/execute` 경로와 ControlBus 소비자 모두 회귀 테스트를 갖췄습니다 (`qmtl/services/gateway/world_client.py#L382-L430`, `qmtl/services/gateway/routes/rebalancing.py#L34-L160`, `tests/qmtl/services/gateway/test_rebalancing_route.py#L100-L174`, `tests/qmtl/services/gateway/test_controlbus_consumer.py#L252-L403`). 다만 Radon 계획에서 요구하는 `/rebalancing/execute` 듀얼 계약 픽스처 연결은 여전히 남아 있습니다.
- **#1511 – SDK Runtime:** 파서·문서·헬스 소비 외에 `alpha_performance` 노드가 `alpha_performance.<metric>` 네임스페이스로 값을 내보내고 Runner/CLI/백테스트 테스트가 이를 검증합니다 (`qmtl/runtime/transforms/alpha_performance.py#L124-L178`, `qmtl/runtime/sdk/runner.py#L667-L687`, `tests/qmtl/interfaces/cli/test_report_cli.py#L8-L21`, `tests/qmtl/runtime/sdk/test_backtest_contracts.py#L135-L155`). 전체 timeout preflight와 런타임/SDK 전 스위트 실행은 아직입니다.
- **테스트 샘플 (2025-11-13):** `uv run -m pytest -W error -n auto tests/qmtl/services/worldservice/test_worldservice_api.py tests/qmtl/services/gateway/test_rebalancing_route.py tests/qmtl/runtime/test_alpha_metrics.py tests/qmtl/runtime/sdk/test_runner_health.py` ✅ — hang-preflight 및 전체 gateway/runtime 스위트는 아직 실행이 필요합니다.

## 마일스톤 체크리스트

### 1. WorldService (문서/스키마/게이트)

- [x] `MultiWorldRebalanceRequest` / `RebalancePlanModel`에 `schema_version` 필드를 추가하고 기본값을 `1`로 유지한다 — 구현: `qmtl/services/worldservice/schemas.py:253-274`, `qmtl/services/worldservice/routers/rebalancing.py:54-187`, 테스트 `tests/qmtl/services/worldservice/test_worldservice_api.py:242-355`.
- [x] `alpha_metrics` (per_world/per_strategy)와 `rebalance_intent.meta` 필드를 v2 gate로 추가하고, v1에서는 자동으로 제거한다 — v2 응답에서는 기본 intent 메타가 채워지고 v1 응답에서는 필드가 완전히 제거된다 (`qmtl/services/worldservice/schemas.py:248-281`, `qmtl/services/worldservice/routers/rebalancing.py:70-219`, `tests/qmtl/services/worldservice/test_worldservice_api.py:322-480`).
- [x] `alpha_metrics` 봉투는 `alpha_performance.<metric>` 네임스페이스를 사용하며, raw 데이터가 없을 경우 모든 값을 `0.0`으로 기본 설정하여 downstream 파서를 간단히 유지한다 (`qmtl/services/worldservice/alpha_metrics.py:1-84`, `tests/qmtl/services/worldservice/test_worldservice_api.py:314-319`).
- [x] `WorldServiceConfig.compat_rebalance_v2` 플래그를 도입하고, REST `/rebalancing/plan|apply` 응답 및 ControlBus 이벤트에 현재 버전과 플래그를 포함한다 (`qmtl/services/worldservice/config.py:25-110`, `qmtl/services/worldservice/api.py:96-210`, `qmtl/services/worldservice/controlbus_producer.py:23-109`).
- [x] `worldservice.server.compat_rebalance_v2` / `worldservice.server.alpha_metrics_required` 설정을 `create_app()` 경로에 연결해 배포마다 v2 지원 여부(또는 필수 여부)를 제어한다 (`qmtl/services/worldservice/api.py:96-210`, `qmtl/foundation/config.py:470-520`).
- [x] `docs/ko|en/architecture/worldservice.md`, `docs/ko|en/world/rebalancing.md` 에 위 필드를 명시하고 본 체크리스트를 링크한다 (`docs/en/world/rebalancing.md:70-90`, `docs/ko/world/rebalancing.md:70-90`).
- [ ] 테스트: `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` (v1/v2 fixture 포함) — 상기 계약 테스트는 통과했지만 hang-preflight 및 전체 테스트 번들은 아직 실행되지 않았다.

### 2. Gateway/DAG (호환 플래그 + 계약 테스트)

- [x] 새 플래그를 설정 파일에서 관리합니다: `gateway.rebalance_schema_version`(기본 `1`)과 `gateway.alpha_metrics_capable`(기본 `false`)을 WS/SDK v2가 준비된 이후에만 켭니다. 필요하면 `gateway.compute_context_contract` 문자열로 SDK가 참조할 계약 버전을 노출합니다. (`qmtl/services/gateway/config.py:24-110`, `qmtl/foundation/config.py:470-520`, `qmtl/services/gateway/cli.py:137-195`.)
- [x] Gateway health 응답과 `/rebalancing/execute` 핸들러에 `rebalance_schema_version`·`alpha_metrics_capable` 플래그를 추가한다 (`qmtl/services/gateway/gateway_health.py:24-110`, `qmtl/services/gateway/routes/status.py:32-119`, `qmtl/services/gateway/routes/rebalancing.py:24-210`, `tests/qmtl/services/gateway/test_rebalancing_route.py:90-100`).
- [x] `WorldServiceClient.post_rebalance_plan` 경로에서 `schema_version` 협상(요청 시 v2, 실패 시 v1) 및 JSON schema 계약 테스트를 추가한다 (`qmtl/services/gateway/world_client.py:382-430`, `tests/qmtl/services/gateway/test_world_client.py:48-105`, `tests/qmtl/services/gateway/test_rebalancing_route.py:100-174`).
- [x] `/rebalancing/execute` 경로에 v1/v2 dual contract fixture를 추가하고, ControlBus 이벤트 호환성 테스트를 작성한다 — `tests/qmtl/services/gateway/test_rebalancing_execute_contract.py`가 실행 경로를 덮고 `tests/qmtl/services/gateway/test_controlbus_consumer.py`가 WebSocket/ControlBus 메타데이터를 검증한다.
- [ ] Gateway Radon 계획(#1512)에서 정의한 health/submission/ControlBus 계약 테스트와 연동한다 — PR 본문에만 언급되어 있으며 실제 회귀 테스트나 CI 워크플로에는 연결되지 않았다.

### 3. SDK Runtime (파서·문서·메트릭)

- [x] `alpha_performance` 결과를 `alpha_performance.<metric>` 네임스페이스로 내보내고, SDK parser가 존재하지 않는 키는 무시하도록 보강한다 (`qmtl/runtime/transforms/alpha_performance.py:124-178`, `qmtl/runtime/sdk/runner.py:667-687`, `tests/qmtl/interfaces/cli/test_report_cli.py:8-21`, `tests/qmtl/runtime/sdk/test_backtest_contracts.py:135-155`).
- [x] Gateway health의 `alpha_metrics_capable` 플래그를 소비하여 SDK 측 기능 플래그를 자동 전환한다 (`qmtl/runtime/sdk/runner.py:38-74`, `tests/qmtl/runtime/sdk/test_runner_health.py:9-22`).
- [x] `docs/ko|en/guides/sdk_tutorial.md`, `docs/ko|en/reference/report_cli.md`에 새 메트릭 키/단위를 명시한다 (`docs/en/guides/sdk_tutorial.md:270-300`, `docs/ko/guides/sdk_tutorial.md:228-250`, `docs/en/reference/report_cli.md:8-18`, `docs/ko/reference/report_cli.md:8-15`).
- [ ] 테스트: `uv run -m pytest -W error -n auto qmtl/runtime/tests qmtl/runtime/sdk/tests` + preflight timeout — 위의 부분 테스트만 실행했으며 전체 런타임·SDK 스위트 및 timeout preflight는 미실행 상태다.

### 4. 공유 산출물

- [ ] 세 팀이 공용 Google Sheet/Markdown 체크리스트 복사본을 유지(본 문서 참고)하고, v2 전환 전 모든 항목을 ✅ 로 표시한다 — 위 진행 현황 섹션에 최신 리뷰를 기록했으며, 미해결 항목들은 그대로 열린 상태다.
- [ ] QA 리허설: Gateway health → SDK 런타임 → WorldService `/rebalancing/plan` 순서로 흐름을 호출하여 schema_version=2 경로가 성공하는지 확인한다 (리허설 로그/산출물이 아직 없다).
- [ ] 최종 병합 순서: #1512 (Gateway/DAG) → #1511 (SDK runtime) → #1513 (WorldService) → `Fixes #1514` 포함 PR 머지 — 위 항목들이 모두 ✅로 바뀐 뒤 순차 병합한다.

## 검증 커맨드 모음

```bash
# Health & compatibility
uv run --with httpx python scripts/check_gateway_health.py --expect-schema-version 2
# Docs
uv run mkdocs build
# Tests
PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1
uv run -m pytest -W error -n auto qmtl/services/worldservice/tests qmtl/services/gateway/tests qmtl/runtime/sdk/tests
```

모든 항목이 만족되면 PR 본문 및 커밋 메시지에 `Fixes #1514` 를 포함해 자동으로 이 이슈를 닫습니다.
