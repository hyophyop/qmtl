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
: 단일 심볼 신호를 입력받아 `target_percent` 의도를 방출합니다(기본은 주문 형태로 출력). 히스테리시스 기반으로 상태가 바뀔 때만 방출해 체결 과잉을 줄입니다. `to_order=True`인 경우 `price_node` 또는 `price_resolver`를 제공해 사이징 단계가 명시적인 `price` 값을 받도록 해야 하며, 가격을 확보하지 못하면 노드는 오류를 발생시킵니다.

예시)
```python
from qmtl.runtime.transforms.position_intent import PositionTargetNode, Thresholds

intent_node = PositionTargetNode(
    signal=alpha_node,
    symbol="BTCUSDT",
    thresholds=Thresholds(long_enter=0.7, short_enter=-0.7),
    long_weight=+0.10,    # +10%
    short_weight=-0.05,   # -5%
    price_node=price_feed,
)
```

이 노드는 `{"symbol":"BTCUSDT", "target_percent":0.10}` 형태를 출력하므로, 기존 `SizingNode`와 결합할 수 있습니다.

## Intent-first NodeSet 레시피

`make_intent_first_nodeset` 는 `PositionTargetNode` 뒤에 표준 실행 파이프라인(프리트레이드 → 사이징 → 실행 → 퍼블리싱)을 구성합니다. 시그널 노드와 이에 대응하는 가격 노드를 입력으로 사용하며, 기본 히스테리시스(`long_enter=0.6`, `short_enter=-0.6`, `long_exit=0.2`, `short_exit=-0.2`)를 적용하고 별도의 포트폴리오/계정을 넘기지 않으면 `initial_cash=100_000` 으로 사이징을 초기화합니다.

```python
from qmtl.runtime.nodesets.recipes import (
    INTENT_FIRST_DEFAULT_THRESHOLDS,
    make_intent_first_nodeset,
)
from qmtl.runtime.sdk.node import StreamInput

signal = StreamInput(tags=["alpha"], interval=60, period=1)
price = StreamInput(tags=["price"], interval=60, period=1)

nodeset = make_intent_first_nodeset(
    signal,
    world_id="demo",
    symbol="BTCUSDT",
    price_node=price,
    thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
    long_weight=0.25,
    short_weight=-0.10,
)

strategy.add_nodes([signal, price, nodeset])  # NodeSet 은 반복 가능
```

어댑터 형태가 필요하면 `IntentFirstAdapter` 를 사용해 `signal`/`price` 입력 포트를 노출하고 `initial_cash` 나 `execution_model` 같은 선택적 파라미터를 그대로 전달할 수 있습니다.

{{ nav_links() }}

