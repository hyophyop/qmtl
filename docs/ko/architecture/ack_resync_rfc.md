---
title: "ACK/Gap Resync RFC (초안)"
tags: [architecture, worldservice, controlbus, rfc]
author: "QMTL Team"
last_modified: 2026-02-06
status: draft
---

{{ nav_links() }}

# ACK/Gap Resync RFC (초안)

## 1. 문제 정의

Core Loop의 2-Phase Apply(`Freeze/Drain -> Switch -> Unfreeze`)에서 `ActivationUpdated.requires_ack=true` 이벤트가 도입되었지만, 다음 항목은 문서 간 규범이 완전히 일치하지 않습니다.

- ACK의 의미: Gateway 수신/적용 확인인지, SDK/WebSocket 하위 소비자까지 포함한 종단 확인인지.
- Apply 완료 조건: WorldService가 ACK 스트림 수렴을 하드 게이트로 기다려야 하는지 여부.
- sequence gap 처리: timeout, 재시도, 강제 resync의 기본값과 실패 시 동작.

이 모호성은 운영 중 freeze 해제 타이밍, 주문 게이트 유지 시간, 장애 복구 절차를 불명확하게 만들어 설계 드리프트 위험을 유발합니다.

## 2. 현재 상태(구현 기준)

관련 문서: [WorldService](worldservice.md), [ControlBus](controlbus.md), [Architecture](architecture.md)

- WorldService는 activation 이벤트에 `phase`, `requires_ack`, `sequence`를 포함해 발행합니다.
- Gateway는 `(world_id, run_id)`별 `sequence` 선형 재생을 강제하며, `control.activation.ack`로 ACK를 게시합니다.
- 현재 구현에서 ACK는 Gateway 수신/적용 확인이며, SDK/WebSocket 하위 ACK를 기다리는 2단 ACK는 구현 필수가 아닙니다.
- 현재 WorldService apply 완료는 ACK 스트림 수렴을 하드 블로킹하지 않습니다.

## 3. 목표와 비목표

목표
- ACK 의미를 단일 정의로 고정하고 문서/운영 절차를 정렬한다.
- sequence gap 발생 시 기본 재동기화 경로를 명시한다.
- 기존 동작을 즉시 깨지 않고 단계적으로 강화 가능한 기준을 제시한다.

비목표
- 본 RFC만으로 SDK/WebSocket 종단 ACK 프로토콜을 강제 도입하지 않는다.
- ControlBus 전송 보장(at-least-once) 자체를 exactly-once로 변경하지 않는다.

## 4. 옵션 비교

### 옵션 A: Gateway 단일 ACK + HTTP resync 기본화

- 정의: ACK는 Gateway가 이벤트를 순서대로 적용한 확인으로 고정.
- gap 처리: timeout 후 `state_hash` 점검 및 HTTP snapshot reconcile 수행.
- 장점: 현재 구현과 가장 일치하며 도입 비용이 낮다.
- 단점: 하위 소비자 전달 보장은 별도 계층(관측/재전송)으로 남는다.

### 옵션 B: 2단 ACK(하위 소비자 ACK 포함)

- 정의: Gateway ACK 이후 SDK/WebSocket 하위 ACK까지 수렴해야 unfreeze 허용.
- 장점: 종단 전달 보장에 가까운 제어가 가능하다.
- 단점: 프로토콜·상태 저장·타임아웃·부분 실패 처리 복잡도가 크게 증가한다.

### 옵션 C: ACK 비중 축소, 주기적 snapshot 동기화 중심

- 정의: sequence ACK를 약화하고 주기적 full snapshot reconcile을 기본으로 운영.
- 장점: 프로토콜 단순화.
- 단점: freeze/unfreeze의 짧은 제어 창에서 지연/오작동 탐지가 늦어진다.

## 5. 권고 기본값(선택)

기본 권고안은 **옵션 A**입니다.

- ACK 의미: `requires_ack=true`는 Gateway 단일 ACK를 의미한다.
- 게이트 규칙: Gateway는 선행 sequence가 적용/ACK되기 전까지 후행 이벤트(특히 unfreeze)를 적용하지 않는다.
- gap timeout 기본값(권고): `activation_gap_timeout_ms=3000`.
- gap 발생 시 기본 절차:
  1. 해당 `(world_id, run_id)` 스트림에서 주문 게이트 유지(닫힘).
  2. `GET /worlds/{world_id}/activation/state_hash`로 divergence 확인.
  3. 필요 시 `GET /worlds/{world_id}/activation` snapshot 조회 후 로컬 상태 재동기화.
  4. 재동기화 성공 전까지 unfreeze 적용 금지.
- apply 완료 의미: 현행대로 WorldService의 apply 완료는 ACK 스트림 수렴을 하드 블로킹하지 않는다.

## 6. 오픈 질문

- Q1. apply 완료를 ACK 스트림 기반으로 강하게 결합할지(옵션 B 일부) 여부.
- Q2. `activation_gap_timeout_ms` 기본값을 3초로 둘지, 환경별(로컬/원격) 프로파일링 후 조정할지.
- Q3. 강제 resync 실패 시 표준 동작을 `freeze 유지 + 운영자 개입`으로 고정할지, 자동 롤백까지 확장할지.
- Q4. ACK 토픽 보관 기간(예: 1h vs 24h)과 운영 비용의 균형.

## 7. 마이그레이션 및 롤아웃 계획

1. 문서 계약 잠금(현재 변경):
   - architecture/worldservice/controlbus 문서에 동일 의미 반영.
2. 관측 강화:
   - `controlbus_apply_ack_latency_ms`, gap 검출 카운터, reconcile 성공/실패 지표를 운영 대시보드에 추가.
3. 기능 플래그 도입:
   - `activation_resync_enforced`(기본 off)로 gap timeout 후 강제 resync 경로를 점진 활성화.
4. 점진 롤아웃:
   - dev -> canary world -> prod 전체 순으로 확장.
5. 안정화 후:
   - 필요 시 apply 완료 조건과 ACK 수렴 결합(옵션 B 일부)을 별도 RFC로 재평가.

## 8. 테스트 계획

- 단위 테스트
  - sequence 정렬/버퍼링/중복 제거.
  - gap timeout 발생 시 resync 트리거.
- 통합 테스트
  - Freeze/Unfreeze 이벤트 순서 역전, 중복, 누락 상황에서 주문 게이트 유지 검증.
  - `state_hash` mismatch 시 HTTP reconcile 경로 검증.
- E2E 테스트
  - world apply 시나리오에서 unfreeze 이전 ACK 처리와 safe fallback 검증.
  - 장애 주입(ACK 토픽 지연/유실, WS 일시 장애)에서 freeze 유지/복구 시간 검증.

## 9. 호환성 및 위험

- 하위 호환성: 옵션 A는 현재 구현과 정렬되어 즉시 breaking change를 요구하지 않습니다.
- 위험: gap timeout이 과도하게 짧으면 불필요한 resync가 증가할 수 있으므로 운영 지표 기반 튜닝이 필요합니다.

{{ nav_links() }}
