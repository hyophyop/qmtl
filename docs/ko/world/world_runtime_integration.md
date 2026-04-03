---
title: "월드 런타임 통합"
tags: [world, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 런타임 통합

본 문서는 월드가 Runner/CLI의 실행 모드와 활성화 게이트를 어떻게 구동하는지 정리합니다. 월드 자체의 상위 계약은 [월드 사양](world.md), SSOT 경계는 [WorldService](../architecture/worldservice.md)와 [Gateway](../architecture/gateway.md)를 따릅니다.

## 1. 단일 진입점

- CLI:
  - `qmtl tools sdk run --world-id <id> --gateway-url <url>`
  - `qmtl tools sdk offline`
- SDK:
  - `Runner.submit(strategy_cls, world=...)`
  - `Runner.offline(...)`

핵심 규칙은 Runner가 자체적으로 실행 모드를 선택하지 않는다는 점입니다. 월드가 산출한 결정과 활성화 엔벌로프가 실행 경로를 제어합니다.

## 2. 실행 흐름

1. Runner가 `world_id`를 받으면 Gateway `GET /worlds/{id}/decide`를 호출합니다.
2. Gateway는 WorldService 결정에서 `effective_mode`를 읽고, 필요한 경우 안전 강등된 `compute_context`를 덧붙여 전달합니다.
3. Runner는 이 결정을 읽기 전용 입력으로 취급하고 주문 게이트/검증 모드를 조정합니다.
4. 활성화 상태는 `GET /worlds/{id}/activation` 또는 이벤트 스트림 부트스트랩으로 보강됩니다.

## 3. 폴백 규칙

- Gateway 응답이 없거나 결정 TTL이 만료되면 fail-closed 기본값을 사용합니다.
- 활성화 정보가 미상·만료면 주문 경로는 열지 않습니다.
- `--world-file` 기반 로컬 재현은 동일한 정책 입력을 사용하되, 권한 있는 실전 활성화 판정은 대체하지 않습니다.
- 어떠한 폴백도 월드가 제공하는 권한 있는 `effective_mode`를 상향 대체해서는 안 됩니다.

## 4. 주문 게이트와의 상호작용

- 모드 결정과 활성화는 서로 다른 엔벌로프지만, 런타임에서는 함께 해석됩니다.
- `effective_mode`가 `paper` 또는 `live`라도 활성화가 닫혀 있으면 주문은 차단됩니다.
- 2-Phase apply 동안 Freeze/Drain 상태에서는 주문 게이트가 우선입니다.

주문 게이트의 상세 계약은 [월드 주문 게이트](world_order_gate.md), 이벤트 스트림은 [월드 이벤트 스트림 런타임](../architecture/world_eventstream_runtime.md)을 참조합니다.

## 5. 즉시 라이브 월드

즉시 실전용 월드는 별도 허가 레일이 필요합니다.

- `allow_live` 또는 동등한 world-scope 권한이 명시되어야 합니다.
- 관측·표본·리스크 가드가 완화되더라도 안전 강등 경로는 제거하지 않습니다.
- 운영자는 world 단위 RBAC와 감사 로그를 통해 live 경로를 추적할 수 있어야 합니다.

{{ nav_links() }}
