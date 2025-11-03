---
title: "의도 기반 포지션 타깃 API"
tags: [sdk, intent]
last_modified: 2025-11-04
---

# 의도 기반 포지션 타깃 API

전략 노드는 주문을 직접 생성하지 않고 "목표 포지션(의도)"만 선언합니다. 실행 계층은 포지션 스냅샷을 기준으로 목표에 수렴하도록 주문을 생성합니다.

## 객체

PositionTarget
- symbol: `str`
- target_percent: `float | None` — 포트폴리오 총가치 대비 비중(±)
- target_qty: `float | None` — 목표 절대 수량(±)
- reason: `str | None`

## 헬퍼

`to_order_payloads(intents, price_by_symbol=None)`
: `PositionTarget` 리스트를 기존 "주문 형태" 딕셔너리로 변환합니다. `target_percent`나 `quantity` 필드를 포함하므로, 기존 `SizingNode`로 수량을 계산할 수 있습니다.

## 노드

`PositionTargetNode`
: 단일 심볼 신호를 입력받아 `target_percent` 의도를 방출합니다(기본은 주문 형태로 출력). 히스테리시스 기반으로 상태가 바뀔 때만 방출해 체결 과잉을 줄입니다.

예시)
```python
from qmtl.runtime.transforms.position_intent import PositionTargetNode, Thresholds

intent_node = PositionTargetNode(
    signal=alpha_node,
    symbol="BTCUSDT",
    thresholds=Thresholds(long_enter=0.7, short_enter=-0.7),
    long_weight=+0.10,    # +10%
    short_weight=-0.05,   # -5%
)
```

이 노드는 `{"symbol":"BTCUSDT", "target_percent":0.10}` 형태를 출력하므로, 기존 `SizingNode`와 결합할 수 있습니다.

{{ nav_links() }}

