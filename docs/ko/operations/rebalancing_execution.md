---
title: "리밸런싱 실행 어댑터"
tags: [operations, rebalancing]
last_modified: 2025-11-04
---

# 리밸런싱 실행 어댑터

`/rebalancing/plan` 으로부터 생성된 월드별 계획을 기존 주문 파이프라인이 소비할 수 있는 주문 페이로드로 변환합니다. `submit=true` 로 호출하면 Gateway가 Commit Log로 배치를 전송해 StrategyManager/CommitLog 경로를 통해 브로커로 전달합니다. 기본값(`submit` 미지정)은 계산된 주문만 반환하며 부작용이 없습니다. 감축 주문에는 여전히 **reduce-only** 플래그를 부여해 과도한 체결을 방지합니다.

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
    - `submit=true|false` (기본 false, Commit Log 경로로 배치 전송)
  - 응답: `{ orders_per_world: { world_id: [order_dict...] }, orders_global?: [order_dict...], orders_per_strategy?: [ {world_id, order} ... ] }`

모드 선택
- 요청 바디에 `mode`를 지정하세요(`scaling` 기본).
- `overlay`/`hybrid`는 현재 미구현이며 호출 시 NotImplementedError가 발생합니다.

공유계정 모드가 아닌 경우에는 **월드별** `per_world` 결과만 실행하고, `global_deltas`는 분석용으로만 사용하세요. `shared_account=true` 인 경우 Gateway는 `scope="global"` 배치를 `per_world` 배치와 함께 기록해 다운스트림 소비자가 원하는 집계 레벨을 선택할 수 있습니다.

## 제출 동작

- **라이브 가드:** `submit=true` 요청은 `X-Allow-Live: true` 헤더가 필요합니다(`enforce_live_guard` 비활성화 시 제외). 헤더가 없으면 403 응답을 반환합니다.
- **거래소 정책:** 로트 사이즈, 최소 거래 노미널, 거래소별 지원 여부를 고려해 주문을 보정합니다. reduce-only를 지원하지 않는 거래소에는 플래그를 제거하고, IOC가 필요한 거래소에는 `time_in_force="IOC"`가 자동으로 지정됩니다.
- **메트릭:** 제출된 각 배치는 `rebalance_batches_submitted_total`, `rebalance_last_batch_size`, `rebalance_reduce_only_ratio` Prometheus 지표(world_id, scope 라벨)를 갱신합니다.
- **감사 로그:** 각 배치는 `rebalance:<world_id>` 키로 `append_event`에 기록되어 주문 수와 reduce-only 비율을 남깁니다.
- **Commit Log:** 배치는 `("gateway.rebalance", timestamp_ms, batch_id, payload)` 형태로 Commit Log에 기록되며 `payload`에는 scope, 주문 목록, 공유 계정 여부, reduce-only 비율, 모드 등이 포함됩니다.

{{ nav_links() }}
