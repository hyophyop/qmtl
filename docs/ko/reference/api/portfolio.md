---
title: "포트폴리오 & 포지션 API"
tags:
  - sdk
  - portfolio
last_modified: 2026-04-24
---

{{ nav_links() }}

# 포트폴리오 & 포지션 API

이 문서는 포트폴리오/포지션 API와 주문을 포트폴리오 비중 또는 금액으로 표현하는 헬퍼 함수를 개괄합니다.

## 객체

Position
- symbol: ``str``
- quantity: ``float``
- avg_cost: ``float``
- market_price: ``float``
- market_value: ``float`` *(property)*
- unrealized_pnl: ``float`` *(property)*

Portfolio
- cash: ``float``
- positions: ``Dict[str, Position]``
- get_position(symbol) -> ``Position | None``
- apply_fill(symbol, quantity, price, commission=0.0)
- total_value *(property)*: 각 보유 종목의 ``market_price`` 를 사용해 총 가치를 계산합니다. 새로 관측한 가격으로 사이징하려면 먼저 해당 포지션을 해당 가격으로 마크하거나, 마크투마켓 조정을 포함하는 헬퍼를 사용하세요.

## 헬퍼

``order_value(symbol, value, price)``
: 지정한 명목 가치 ``value`` 에 해당하는 수량을 반환합니다.

``order_percent(portfolio, symbol, percent, price)``
: 현재 포트폴리오 가치의 ``percent`` 만큼 주문을 사이징합니다.

``order_target_percent(portfolio, symbol, percent, price)``
: ``symbol`` 의 목표 비중을 달성하도록 리밸런싱합니다.

이 헬퍼는 부호가 있는 수량을 반환하며 기존 주문 생성 루틴과 결합해 사용할 수 있습니다.

## 로컬 PnL 진단 헬퍼

빠른 전략 반복 검증에서는 `qmtl.runtime.sdk.diagnostics.summarize_account_pnl` 을 선택적으로 사용할 수 있습니다. 이 헬퍼는 로컬 fill 목록과 선택적 mark 가격을 받아 계정 단위 `ending_cash`, `equity`, `realized_pnl`, `unrealized_pnl`, `fees`, `total_pnl`, open position 요약을 반환합니다.

```python
from qmtl.runtime.sdk.diagnostics import AccountFill, summarize_account_pnl

summary = summarize_account_pnl(
    [
        AccountFill("AAPL", 10, 100.0, commission=1.0),
        AccountFill("AAPL", -4, 110.0, commission=0.5),
    ],
    marks={"AAPL": 120.0},
    starting_cash=1_000.0,
)

assert summary.total_pnl == 158.5
```

이 표면은 로컬 iteration용 opt-in 진단 도구입니다. `Runner.submit(..., world=...)`, Gateway/WorldService, portfolio/risk hub의 권위 모델을 변경하지 않습니다.

{{ nav_links() }}
