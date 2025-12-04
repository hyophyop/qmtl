---
title: "월드 활성화 런북 — Freeze/Drain/Switch/Unfreeze"
tags: [operations, runbook, world]
author: "QMTL SRE"
last_modified: 2025-08-29
---

{{ nav_links() }}

# 월드 활성화 런북 — Freeze/Drain/Switch/Unfreeze

## 시나리오
- 계획된 승격/강등
- 비상 회로(특정 월드의 모든 주문 비활성화)
- 적용 실패 후 롤백

## 사전 조건
- WorldService와 Gateway 노드의 NTP 상태 확인
- `world_id`, 현재 `resource_version`/`etag` 파악

## WS SSOT & 클라이언트 노출
- WorldService 평가/활성 결과가 `status/weight/contribution`의 단일 진실(SSOT)입니다. CLI/SDK `submit`은 WS 출력 그대로를 노출합니다.
- 로컬 ValidationPipeline 결과는 “pre-check”(비권위) 섹션으로 분리됩니다. 불일치 시 WS 메트릭/로그를 우선 확인하고 pre-check는 참고용으로 사용합니다.
- `downgraded/safe_mode/downgrade_reason`은 기본 안전 강등 여부를 표시하기 위해 최상단에 유지됩니다.

## 절차

1) Freeze/Drain
- `/worlds/{id}/activation` 에 `{ active:false }` 오버라이드를 적용하거나 회로 차단 플래그 추가
- SDK 메트릭/로그를 통해 주문 게이트가 OFF 상태인지 확인

2) Apply(Switch)
- `/worlds/{id}/evaluate` 로 플랜 생성
- 플랜을 검토한 뒤 `run_id` 와 함께 `/worlds/{id}/apply` 호출
- `world_apply_duration_ms` 및 감사 로그로 완료 여부 모니터링

3) Unfreeze
- 회로/오버라이드를 제거하고 ActivationEnvelope etag가 증가했는지 확인

## 롤백
- 적용 실패 또는 회귀 발견 시 감사 로그에 기록된 이전 활성화 스냅샷으로 복구
- `GET /worlds/{id}/activation` 과 SDK 동작을 통해 상태를 재확인

## 경보 & 대시보드
- 경보: `promotion_fail_total`, `activation_skew_seconds`, `stale_decision_cache`
- 대시보드: `world_decide_latency_ms_p95`, 이벤트 팬아웃 지연, Gateway 프록시 오류율
- `pretrade_attempts_total{world_id="demo"}` 같은 월드 범위 메트릭으로 월드별 활성화 상태를 검증하세요.

{{ nav_links() }}
