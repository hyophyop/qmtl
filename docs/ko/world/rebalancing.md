---
title: "중앙집중형 리밸런싱 정책"
tags: [world, rebalancing]
author: "QMTL Team"
last_modified: 2025-11-04
---

# 중앙집중형 리밸런싱 정책

본 문서는 전략 노드가 "의도(Intent)"만 방출하는 설계를 유지하면서, 월드/전략 할당 비율 변화에 따라 포지션을 중앙집중형으로 조정하는 리밸런싱 모듈의 규격과 기본 규칙 기반 구현을 설명합니다.

## 목표

- 월드 할당(`world_alloc`) 및 월드 내 전략 할당(`strategy_alloc`) 변화가 발생하면 자동으로 포지션을 증감.
- 다종목·다전략 포지션을 거래소/종목 단위로 중앙에서 넷팅하여 불필요한 체결·수수료를 최소화.
- 주문 상태 조회 없이도 "포지션 스냅샷 기반 수렴" 정책으로 실행 가능.
- 초기에는 규칙 기반(비례 축소/확대)으로 시작하고, 이후 다른 모듈로 교체 가능한 플러그형 인터페이스 제공.

## 데이터 계약

- 입력 스냅샷: `PortfolioSnapshot`(참조: reference/api/portfolio.md, reference/schemas/portfolio_snapshot.schema.json)
  - `positions[symbol] = { qty, avg_cost, mark }`
  - 전략 단위로 스냅샷을 수집하여 `(world_id, strategy_id)` 스코프로 전달
- 리밸런싱 컨텍스트:
  - `total_equity`: 총자산(모든 월드 합)
  - `world_alloc_before/after`: 월드 할당 비율(0.0–1.0)
  - `strategy_alloc_before/after`: 전략별 총자산 대비 비율(0.0–1.0)
  - `positions`: 전략 식별자와 선택적 `venue`(거래소)까지 포함한 플래튼 행
  - `min_trade_notional`, `lot_size_by_symbol`: 소액 트레이드 억제/라운딩

## 규칙: 비례 리밸런싱(Proportional)

- 월드 스케일: `gw = world_after / world_before` (감소 사례: 0.3 → 0.2 이면 2/3)
- 전략 스케일: `gs[s] = strategy_after[s] / strategy_before[s]` (없으면 `gw` 적용)
- 유효 스케일:
  - 감소 시: `g = min(gw, gs[s])`
  - 증가 시: `g = max(gw, gs[s])`
- 각 전략 포지션의 표기가치(`qty * mark`)에 `g`를 곱해 목표 표기가치를 산출하고, 현재 대비 델타(증감)를 계산
- 동일 (거래소, 심볼) 키로 델타를 합산하여 중앙집중형으로 넷팅
- `min_trade_notional` 미만은 생략, 필요 시 `lot_size`로 라운딩

예시)
- a 월드가 총자산의 0.3 → 0.2 로 감소하면 `gw = 2/3`
- a 월드 b 전략이 0.1(= 0.3의 1/3) → 비율 고정이라면 `gs[b] = 2/3`
- 각 보유 포지션은 표기가치를 2/3로 축소하도록 중앙에서 델타를 합산해 주문을 생성(실행 계층은 포지션 기반 수렴)

## 인터페이스와 기본 구현

- 인터페이스: `qmtl/services/worldservice/rebalancing/base.py`
  - `Rebalancer.plan(RebalanceContext) -> RebalancePlan`
  - 출력은 (거래소, 심볼)별 `delta_qty` 목록과 스케일링 정보
- 기본 구현: `ProportionalRebalancer`
  - 위 비례 스케일 규칙을 적용
  - 넷팅 및 소액 제거/라운딩 지원
  - 결합 규칙: 전략 비중이 총자산 기준으로 주어지면 `g_s = after_total/ before_total`을 그대로 적용(전략 벡터 스케일). 전략 비중이 없으면 월드 스케일을 캐스케이드(`g_w = world_after/world_before`).

## 다중 월드 동시 계획(Multi‑World Planning)

- 여러 월드의 비중을 한 번에 조정하면, (동일 거래소/심볼 기준) 상쇄되는 증감 노출을 중앙에서 넷팅해 수수료를 줄일 수 있습니다.
- 컨텍스트와 계획 타입
  - 입력: `MultiWorldRebalanceContext`
    - `world_alloc_before/after`: 월드별 비중(총자산 대비)
    - `strategy_alloc_*_total`: 선택(없으면 "월드 스케일 캐스케이드" 사용)
    - `positions`: 모든 월드의 포지션(각 행은 `world_id` 포함)
  - 출력: `MultiWorldRebalancePlan`
    - `per_world`: 월드별 `RebalancePlan`
    - `global_deltas`: 전 월드 합산 넷 뷰(분석/공유계정 넷팅용)
- 구현: `MultiWorldProportionalRebalancer`
  - 각 월드에 `ProportionalRebalancer`를 적용하고, 전역 넷 델타를 추가 계산합니다.
  - 실제 주문은 안전하게 월드별로 실행하고, 공유 계정 모드에서만 `global_deltas`를 넷팅 근거로 사용할 것을 권장합니다.

## 전략 비중 조절 트리거와 캐스케이드

- 수동 조절은 지원하지 않습니다. 전략 비중은 두 가지 트리거로만 변경됩니다.
  1) 월드 내 성과 기반 가중치(백테스트 PnL/지표) 모듈이 갱신한 결과
  2) 월드 비중 리밸런싱의 캐스케이드(전략 상대비율은 유지, 월드 스케일만 반영)
- 리밸런서 사용법
  - 성과 모듈이 전략 비중을 갱신한 경우: `strategy_alloc_after_total`을 제공하여 해당 비중을 반영
  - 그렇지 않은 경우: 생략하면 월드 스케일만 전략에 캐스케이드되어 기존 전략 간 분배는 유지

## 실행 계층과의 결합

- 리밸런서 출력의 `delta_qty`는 실행 노드에서 포지션 스냅샷 기반으로 수렴시키면 됩니다.
  - 감소: `reduce-only` 부분청산(지원 시)
  - 증가: 잔여 델타만 신규 진입
  - 반전 필요 시 "flatten-then-open" 또는 안전장치가 포함된 "direct-flip" 정책 사용(참조: architecture/execution_nodes.md)

## 교체 가능한 설계(플러그형)

- 동일 인터페이스로 비용 민감, 슬리피지 인지, 리스크 제약(VaR/마진) 포함 모델로 교체 가능
- 교체 모듈은 동일 입력(`RebalanceContext`)을 사용하고, 동일 출력(`RebalancePlan`)을 제공

## 주의 사항

- 거래소/심볼별 라운딩 및 최소 주문 단위를 반영하지 않으면 과/과소 체결이 발생할 수 있습니다.
- 주문 상태는 신뢰하지 않는 전제에서, 실행 계층은 반드시 "포지션 스냅샷"만을 진실로 삼아야 합니다.
- 거래소 간 심볼 코드 차이를 `venue`/심볼 정규화 단계에서 해결하세요.

{{ nav_links() }}

{{ nav_links() }}
