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

## 2‑Phase Apply 절차 (운영 표준)

1) Freeze/Drain — 회로 차단
- `PUT /worlds/{id}/activation`에 `{active:false}` 오버라이드 적용 또는 CLI:  
  `uv run qmtl world activation set <world> --active=false --reason maintenance --etag <etag>`
- SDK/Gateway 메트릭으로 주문 게이트 OFF(`pretrade_attempts_total` 감소) 확인

2) Evaluate — 계획 생성
- `POST /worlds/{id}/evaluate` 또는 CLI: `uv run qmtl world eval <world> --output json --as-of ...`
- 결과에 포함된 `ttl/etag/run_id`를 기록해 apply 입력으로 사용

3) Apply (Switch) — 계획 적용
- `POST /worlds/{id}/apply` with `run_id` (필수) · `etag` (낙관 잠금)  
  CLI 예: `uv run qmtl world apply <world> --plan plan.json --run-id $(uuidgen) --etag <etag>`
- 모니터링: `world_apply_duration_ms`, `activation_skew_seconds`, 감사 로그(`world:<id>:activation`)

4) Unfreeze — 회로 해제
- 오버라이드 제거 후 ActivationEnvelope `etag` 증가/유효 TTL 확인:  
  `uv run qmtl world activation get <world>`

## 롤백
- Apply 실패나 회귀 발견 시 감사 로그에 저장된 직전 활성 스냅샷을 복원(`activation set`).
- SDK/CLI가 surfacing 하는 WS 봉투로 최종 상태를 재확인하고, `promotion_fail_total` 경보 해제까지 추적합니다.

## 경보 & 대시보드
- 경보: `promotion_fail_total`, `activation_skew_seconds`, `stale_decision_cache`
- 대시보드: `world_decide_latency_ms_p95`, ControlBus 팬아웃 지연, Gateway 프록시 오류율
- 월드 범위 메트릭(`pretrade_attempts_total{world_id="demo"}`)으로 회로 차단·해제 여부를 교차 검증하세요.

{{ nav_links() }}
