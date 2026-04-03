---
title: "월드 롤아웃 및 운영"
tags: [world, rollout, operations]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 롤아웃 및 운영

본 문서는 월드 기능을 운영 환경에 도입할 때 필요한 안전장치, 단계적 롤아웃, 멀티-월드 자원 정책을 정리합니다. 규범 인터페이스는 [월드 사양](world.md), 세부 운영 절차는 [운영 문서](../operations/README.md)를 참조합니다.

## 1. 필수 안전장치

- 데이터 통화성 게이트: `now - data_end <= max_lag` 충족 전에는 compute-only를 유지합니다.
- 표본 충분성: 최소 기간/체결 수를 충족하기 전의 결과는 참고용으로만 사용합니다.
- 2-Phase 전환: `Freeze/Drain -> Switch -> Unfreeze`를 idempotent `run_id`로 추적합니다.
- apply는 `run_id`/`etag` 기반으로 요청하고 감사 로그에서 추적 가능해야 합니다.
- 월드 수준 드로우다운, VaR, 레버리지 상한 위반 시 즉시 게이트를 닫습니다.

## 2. 권장 SLO와 알람

핵심 지표:

- `world_eval_duration_ms_p95`
- `world_apply_duration_ms_p95`
- `world_activation_skew_seconds`
- `promotion_fail_total`
- `demotion_fail_total`
- `world_apply_failure_total`
- `world_apply_run_total`
- `world_allocation_snapshot_stale_ratio`
- `controlbus_apply_ack_latency_ms{phase}`

권장 알람:

- `increase(world_apply_failure_total[5m]) > 0`
- `world_allocation_snapshot_stale_ratio > 0.1`
- `world_activation_skew_seconds > 5`

## 3. 멀티-월드와 자원 격리

- 기본 전략은 World-SILO 격리입니다.
- 비용 최적화를 위해 공유 노드를 도입하더라도 NodeID 해시/네임스페이스 경계를 먼저 고정해야 합니다.
- shared node 도입 시 Mark-and-Sweep는 Drain과 함께 수행해야 합니다.

## 4. 단계적 도입

### Phase 0

- world 정책 문서와 샘플 YAML 정비
- 지표 산출 노드 또는 기존 메트릭 노출 정리

### Phase 1

- 읽기 전용 평가 엔진과 activation table 도입
- `GET /worlds/{id}/activation`, `POST /worlds/{id}/evaluate`

### Phase 2

- `POST /worlds/{id}/apply`
- 리스크 컷/서킷 브레이커
- 승격/강등/실패/지연 메트릭

### Phase 3

- SDK 주문 게이트 도입
- 전략 예시와 운영 가이드 갱신

### Phase 4

- 멀티-월드 최적화와 shared node 네임스페이스

## 5. Runner/CLI 전환

- `qmtl tools sdk run --world-id ...`
- `qmtl tools sdk offline`
- 문서와 예제는 월드 우선 실행 표면을 기준으로 유지합니다.

실제 운영 플로우와 승인 절차는 다음 문서에 위임합니다.

- [World Activation Runbook](../operations/activation.md)
- [World Validation Governance](../operations/world_validation_governance.md)
- [ControlBus 운영](../operations/controlbus_operations.md)
- [Rebalancing Execution](../operations/rebalancing_execution.md)

{{ nav_links() }}
