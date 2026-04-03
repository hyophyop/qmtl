---
title: "월드 이벤트 스트림 런타임"
tags: [architecture, world, controlbus, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 이벤트 스트림 런타임

본 문서는 월드 활성화/큐/정책 이벤트가 ControlBus 내부 구현을 외부에 노출하지 않은 채 Gateway를 통해 SDK로 전달되는 런타임 경계를 정리합니다. SSOT는 [WorldService](worldservice.md)와 [DAG Manager](dag-manager.md), 내부 팬아웃 패브릭은 [ControlBus](controlbus.md)입니다.

## 1. 역할 분리

- **WorldService**: world/policy/activation SSOT
- **DAG Manager**: graph/node/queue SSOT
- **ControlBus**: 내부 배포/팬아웃 버스. 외부 클라이언트 비공개
- **Gateway**: 외부 단일 접점, 이벤트 스트림 디스크립터 발급과 fan-out
- **SDK/Runner**: 불투명 스트림 소비자

## 2. EventStreamDescriptor

Gateway는 `POST /events/subscribe` 응답으로 불투명한 스트림 디스크립터를 반환합니다.

- `stream_url`: 게이트웨이 도메인 하의 WebSocket URL
- `token`: world/topic/strategy scope가 들어간 JWT
- `topics`: 서버가 정규화한 구독 주제
- `expires_at`: 재구독 시점
- `fallback_url`: 스트림 장애 시 보조 경로

클라이언트는 ControlBus의 실제 구현이나 토픽 이름을 알 필요가 없습니다.

## 3. 이벤트 타입

- `ActivationUpdated`
  - `world_id`, `strategy_id`, `side`, `active`, `weight`, `effective_mode`, `etag`, `run_id`, `ts`
- `QueueUpdated`
  - `tags[]`, `interval`, `queues[]`, `etag`, `ts`
- `PolicyUpdated`
  - `world_id`, `version`, `checksum`, `status`, `ts`

## 4. 순서, 멱등성, 복구

- 순서는 키 단위(`world_id`, `(tags, interval)`)로만 보장합니다.
- 중복은 허용되므로 `etag` 또는 `run_id` 기반 멱등 처리가 필요합니다.
- 스트림 실패 시:
  1. `fallback_url` 또는 HTTP polling 사용
  2. `GET /worlds/{id}/activation` / `GET /queues/by_tag`로 상태 보정
  3. 필요 시 `POST /events/subscribe`로 토큰 재발급

ACK/sequence gap 복구 정책은 [ACK/Gap Resync RFC (초안)](../design/ack_resync_rfc.md)를 참조합니다.

## 5. 인터페이스 개요

- SDK → Gateway
  - `/strategies`, `/queues/by_tag`, `/worlds/*`, `/events/subscribe`
- Gateway → WorldService
  - `/worlds/*`, `/activation`, `/decide`, `/evaluate`, `/apply`
- Gateway → DAG Manager
  - `get_queues_by_tag`, diff/queue queries
- WorldService / DAG Manager → ControlBus
  - activation/policy/queue events publish
- Gateway → ControlBus
  - subscribe 후 SDK로 재송신

## 6. 지연 예산

- SDK → Gateway 제출 p95 ≤ 150ms
- 큐 조회 p95 ≤ 200ms
- 이벤트 fan-out 지연 p95 ≤ 200ms
- activation skew ≤ 2s

실패 기본값은 항상 fail-closed 입니다. 월드 결정을 받지 못하면 compute-only, 활성화 미확인 시 주문 게이트는 닫힙니다.

## 7. 관계 다이어그램

```mermaid
graph LR
  subgraph Client
    SDK[SDK / Runner]
  end
  subgraph Edge
    GW[Gateway]
  end
  subgraph Core
    WS[WorldService (SSOT Worlds)]
    DM[DAG Manager (SSOT Graph)]
    CB[(ControlBus - internal)]
  end

  SDK -- HTTP submit/decide/activation --> GW
  GW -- proxy --> WS
  GW -- proxy --> DM
  WS -- publish --> CB
  DM -- publish --> CB
  GW -- subscribe --> CB
  GW -- opaque stream --> SDK
```

{{ nav_links() }}
