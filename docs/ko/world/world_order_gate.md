---
title: "월드 주문 게이트"
tags: [world, order-gate, activation]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 주문 게이트

본 문서는 월드 활성화 상태를 주문 경로에 반영하는 경량 `OrderGate` 계약을 정리합니다. 활성화 SSOT는 [WorldService](../architecture/worldservice.md), 이벤트 전파는 [월드 이벤트 스트림 런타임](../architecture/world_eventstream_runtime.md)에 따릅니다.

## 1. 목적

- 전략 코드에 최소 침습으로 주문 허용/차단을 삽입합니다.
- 2-Phase apply 중 Freeze/Drain → Switch → Unfreeze 순서를 안전하게 반영합니다.
- 활성화 미상, stale, 권한 부족 상황에서는 fail-closed를 기본값으로 유지합니다.

## 2. 형태와 위치

- 형태: SDK 공용 ProcessingNode 또는 동등한 어댑터(`OrderGateNode`).
- 위치: 주문/브로커리지 노드 직전의 마지막 게이트.
- 기본 정책: 활성화가 명시적으로 열려 있지 않으면 차단 또는 0-size 축소.

## 3. 입력 계약

- HTTP:
  - `GET /worlds/{world_id}/activation?strategy_id=...&side=...`
- 스트림:
  - activation bootstrap frame
  - ControlBus relay를 경유한 activation update

최소 엔벌로프:

```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "effective_mode": "paper",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c..."
}
```

## 4. 동작 규칙

1. `active=false` 이면 주문을 차단합니다.
2. `freeze=true` 또는 `drain=true` 이면 후속 phase가 오기 전까지 주문을 열지 않습니다.
3. stale activation 또는 decision 불가 상태는 `active=false`, `weight=0.0`, `effective_mode=compute-only`로 강등합니다.
4. `weight`는 주문 경로에서 포지션 규모 또는 intent 크기 스케일링에 사용할 수 있지만, 게이트 자체를 우회하는 신호로 해석해서는 안 됩니다.

## 5. 2-Phase apply와의 관계

- Freeze/Drain: 주문 경로 닫힘, 필요 시 reduce-only 또는 평탄화 단계 허용.
- Switch: 활성 세트와 가중치 교체.
- Unfreeze: 선행 sequence와 ACK 규칙이 만족된 뒤에만 주문 경로를 다시 열 수 있습니다.

ACK/sequence 회복 정책은 [ACK/Gap Resync RFC (초안)](../design/ack_resync_rfc.md)와 [ControlBus 운영](../operations/controlbus_operations.md)에서 관리합니다.

## 6. 관측 항목

- `world_activation_skew_seconds`
- `controlbus_apply_ack_latency_ms{phase}`
- `world_apply_failure_total`
- `activation_updated` 수신 카운터와 stale 응답 카운터

운영 대응 절차는 [World Activation Runbook](../operations/activation.md)과 [Determinism Runbook](../operations/determinism.md)을 참조합니다.

{{ nav_links() }}
