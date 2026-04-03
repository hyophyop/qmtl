---
title: "월드 할당 및 리밸런싱 계약"
tags:
  - architecture
  - worldservice
  - rebalancing
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 할당 및 리밸런싱 계약

## 관련 문서

- [WorldService](worldservice.md)
- [Core Loop 계약](../contracts/core_loop.md)
- [월드 라이프사이클 계약](../contracts/world_lifecycle.md)
- [리밸런싱 실행 어댑터](../operations/rebalancing_execution.md)
- [Rebalancing Schema Coordination](../operations/rebalancing_schema_coordination.md)

## 목적

이 문서는 WorldService의 월드 비중 및 리밸런싱 표면을 **별도 규범 계약**으로 분리해 정의한다.

WorldService 문서의 역할은 월드 정책, 결정, 활성화의 SSOT를 설명하는 데 있고,
할당/리밸런싱 계약은 별도의 제어면으로 다루는 편이 더 명확하다.

## 요약

Concept ID: `CTRL-WORLD-ALLOCATION-TWO-STEP`

QMTL은 world allocation과 rebalancing을 다음의 **표준 두 단계 루프**로 본다.

1. 평가/활성화: `Runner.submit(..., world=...)`로 world 상태를 관찰한다.
2. 계획/적용: `/allocations`, `/rebalancing/plan`, `/rebalancing/apply`로 자본 배분과 실행 계획을 다룬다.

핵심 원칙:

- allocation snapshot 노출은 읽기 전용 관측 계약이다.
- 실제 자본 적용과 주문 실행은 감사 가능한 운영 단계다.
- 동일 `run_id`에 대한 멱등성과 `etag` 기반 추적을 유지한다.

## 비목표

- 실제 거래소 주문 변환과 제출 절차 전체를 설명하는 것
- 운영 승인, 롤백, 배치 제출 runbook을 설명하는 것
- 제품 관점의 submit 결과 표면을 다시 설명하는 것

## 표면 요약

### `POST /allocations`

- 월드 비중 및 전략 슬리브 스냅샷을 업서트한다.
- `run_id`와 요청 해시 기반 `etag`로 멱등성을 제공한다.
- 성공 시 최신 allocation snapshot과 관련 실행 결과를 기록한다.
- `execute=true`는 구성된 실행기가 있을 때만 허용된다.

### `POST /rebalancing/plan`

- 상태를 저장하지 않는 순수 계획 계산 표면이다.
- 운영자는 사전 검토, 시뮬레이션, 외부 실행 파이프라인 입력에 사용한다.

### `POST /rebalancing/apply`

- 승인된 플랜을 감사/관측 가능한 형태로 고정한다.
- world allocation 자체를 직접 변경하는 계약이 아니라, 승인된 계획을 기록하고 이벤트로 발행하는 계약이다.

## 멱등성 및 감사

- `run_id`는 재시도와 중복 제출을 식별하는 표준 키다.
- `etag`는 동일 `run_id` 아래 페이로드 불일치를 감지하는 낙관 잠금 역할을 한다.
- 적용 단계는 감사 가능한 운영 경계로 남긴다.

## 스키마 버전 및 alpha 메트릭 핸드셰이크

Concept ID: `CTRL-REBALANCING-SCHEMA-HANDSHAKE`

- `/rebalancing/plan`과 `/rebalancing/apply`는 `schema_version` 협상을 따른다.
- v2가 활성화되면 `alpha_metrics` 봉투가 플랜과 함께 반환된다.
- 필수 메트릭 모드에서는 하위 버전 요청을 조기에 거부할 수 있다.
- ControlBus 이벤트도 협상된 같은 스키마 버전을 따라야 한다.

운영 전환 체크리스트는 [Rebalancing Schema Coordination](../operations/rebalancing_schema_coordination.md)에서 다룬다.

## 읽기 전용 표면과 운영 표면

읽기 전용 표면:

- submit 결과에 surfacing 되는 allocation snapshot
- `GET /allocations?world_id=...` 조회
- `/rebalancing/plan` 결과

운영 표면:

- `/allocations` 업서트
- `/rebalancing/apply`
- 외부 실행기 호출 또는 주문 제출

## 관련 운영 문서

- 주문 변환과 제출 절차는 [리밸런싱 실행 어댑터](../operations/rebalancing_execution.md)에서 다룬다.
- activation/freeze/drain은 [월드 활성화 런북](../operations/activation.md)에서 다룬다.

{{ nav_links() }}
