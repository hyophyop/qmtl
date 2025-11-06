---
title: "리밸런싱 실행 어댑터"
tags: [operations, rebalancing]
last_modified: 2025-11-04
---

# 리밸런싱 실행 어댑터

`/rebalancing/plan` 으로부터 생성된 월드별 계획을 기존 주문 파이프라인이 소비할 수 있는 주문 페이로드로 변환합니다. 이 모듈은 주문 제출을 직접 수행하지 않으며, 안전하게 **reduce-only** 플래그를 부여해 감축 주문의 과도한 체결을 막습니다.

## 모듈

- `qmtl/services/gateway/rebalancing_executor.py`
  - `orders_from_world_plan(plan, options)` → `[order_dict]`
  - `orders_from_strategy_deltas(deltas, options)` → `[order_dict]`

기본 옵션은 `time_in_force="GTC"`, 감축(delta < 0) 시 `reduce_only=True` 입니다.

## 예시

```python
from qmtl.services.worldservice.rebalancing import MultiWorldProportionalRebalancer, MultiWorldRebalanceContext
from qmtl.services.gateway.rebalancing_executor import orders_from_world_plan

# 1) 멀티 월드 계획 생성 (WorldService 내부나 별도 서비스)
result = MultiWorldProportionalRebalancer().plan(ctx)
plan_a = result.per_world["a"]

# 2) 게이트웨이에서 주문 페이로드 생성
orders = orders_from_world_plan(plan_a)
for payload in orders:
    broker_client.post_order(payload)  # 기존 게시 경로 재사용
```

## 라우팅

- 게이트웨이는 WorldService의 `/rebalancing/plan` 엔드포인트를 프록시합니다.
  - 경로: `POST /rebalancing/plan`
  - 바디: `MultiWorldRebalanceRequest`
  - 응답: `MultiWorldRebalanceResponse`

- 실행 편의 엔드포인트
  - 경로: `POST /rebalancing/execute`
  - 바디: `MultiWorldRebalanceRequest`
  - 쿼리:
    - `per_strategy=true|false` (기본 false)
    - `shared_account=true|false` (기본 false, 전월드 넷팅 시 `orders_global` 포함)
  - 응답: `{ orders_per_world: { world_id: [order_dict...] }, orders_global?: [order_dict...], orders_per_strategy?: [ {world_id, order} ... ] }`

모드 선택
- 요청 바디에 `mode`를 지정하세요(`scaling` 기본, `overlay`, `hybrid`).
- 오버레이/하이브리드 모드에서 `overlay_deltas`가 응답에 포함되며, 게이트웨이는 이를 `orders_global`로 변환합니다.

공유계정 모드가 아닌 경우에는 **월드별** `per_world` 결과만 실행하고, `global_deltas`는 분석용으로만 사용하세요.

{{ nav_links() }}
