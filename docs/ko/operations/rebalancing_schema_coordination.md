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

## 마일스톤 체크리스트

### 1. WorldService (문서/스키마/게이트)

- [ ] `MultiWorldRebalanceRequest` / `RebalancePlanModel`에 `schema_version` 필드를 추가하고 기본값을 `1`로 유지한다.
- [ ] `alpha_metrics` (per_world/per_strategy)와 `rebalance_intent.meta` 필드를 v2 gate로 추가하고, v1에서는 자동으로 제거한다.
- [ ] `alpha_metrics` 봉투는 `alpha_performance.sharpe`, `alpha_performance.max_drawdown` 등 `alpha_performance.<metric>` 네임스페이스를 사용하며, raw 데이터가 없을 경우 모든 값을 `0.0`으로 기본 설정하여 downstream 파서를 간단히 유지한다.
- [ ] `WorldServiceConfig.compat_rebalance_v2` 플래그를 도입하고, REST `/rebalancing/plan|apply` 응답 및 ControlBus 이벤트에 현재 버전과 플래그를 포함한다.
- [ ] `worldservice.server.compat_rebalance_v2` / `worldservice.server.alpha_metrics_required` 설정을 `create_app()` 경로에 연결해 배포마다 v2 지원 여부(또는 필수 여부)를 제어한다.
- [ ] `docs/ko|en/architecture/worldservice.md`, `docs/ko|en/world/rebalancing.md` 에 위 필드를 명시하고 본 체크리스트를 링크한다.
- [ ] 테스트: `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` (v1/v2 fixture 포함).

### 2. Gateway/DAG (호환 플래그 + 계약 테스트)

- [ ] 새 플래그를 설정 파일에서 관리합니다: `gateway.rebalance_schema_version`(기본 `1`)과 `gateway.alpha_metrics_capable`(기본 `false`)을 WS/SDK v2가 준비된 이후에만 켭니다. 필요하면 `gateway.compute_context_contract` 문자열로 SDK가 참조할 계약 버전을 노출합니다.
- [ ] Gateway health 응답과 `/rebalancing/execute` 핸들러에 `rebalance_schema_version`·`alpha_metrics_capable` 플래그를 추가한다.
- [ ] `WorldServiceClient.post_rebalance_plan` 경로에서 `schema_version` 협상(요청 시 v2, 실패 시 v1) 및 JSON schema 계약 테스트를 추가한다.
- [ ] `/rebalancing/execute` 경로에 v1/v2 dual contract fixture를 추가하고, ControlBus 이벤트 호환성 테스트(`tests/services/gateway/test_rebalancing_execute_contract.py`)를 작성한다.
- [ ] Gateway Radon 계획(#1512)에서 정의한 health/submission/ControlBus 계약 테스트와 연동한다.

### 3. SDK Runtime (파서·문서·메트릭)

- [ ] `alpha_performance` 결과를 `alpha_performance.<metric>` 네임스페이스로 내보내고, SDK parser가 존재하지 않는 키는 무시하도록 보강한다.
- [ ] Gateway health의 `alpha_metrics_capable` 플래그를 소비하여 SDK 측 기능 플래그를 자동 전환한다.
- [ ] `docs/ko|en/guides/sdk_tutorial.md`, `docs/ko|en/reference/report_cli.md`에 새 메트릭 키/단위를 명시한다.
- [ ] 테스트: `uv run -m pytest -W error -n auto qmtl/runtime/tests qmtl/runtime/sdk/tests` + preflight timeout.

### 4. 공유 산출물

- [ ] 세 팀이 공용 Google Sheet/Markdown 체크리스트 복사본을 유지(본 문서 참고)하고, v2 전환 전 모든 항목을 ✅ 로 표시한다.
- [ ] QA 리허설: Gateway health → SDK 런타임 → WorldService `/rebalancing/plan` 순서로 흐름을 호출하여 schema_version=2 경로가 성공하는지 확인한다.
- [ ] 최종 병합 순서: #1512 (Gateway/DAG) → #1511 (SDK runtime) → #1513 (WorldService) → `Fixes #1514` 포함 PR 머지.

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
