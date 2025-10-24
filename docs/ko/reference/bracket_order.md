# 브래킷 주문 헬퍼

`BracketOrder` 유틸리티는 진입 주문을 제출하고 체결 후 연동된 익절/손절 주문을 `OCOOrder` 로 관리합니다.

예제:

```python
from qmtl.runtime.brokerage import BracketOrder, Order, OrderType, TimeInForce

entry = Order(
    symbol="AAPL",
    quantity=100,
    price=100.0,
    type=OrderType.LIMIT,
    tif=TimeInForce.GTC,
    limit_price=100.0,
)
take_profit = Order(
    symbol="AAPL",
    quantity=-100,
    price=100.0,
    type=OrderType.LIMIT,
    tif=TimeInForce.GTC,
    limit_price=110.0,
)
stop_loss = Order(
    symbol="AAPL",
    quantity=-100,
    price=100.0,
    type=OrderType.STOP,
    tif=TimeInForce.GTC,
    stop_price=90.0,
)
bracket = BracketOrder(entry, take_profit, stop_loss)
```

실행 가능한 예시는 `qmtl/examples/brokerage_demo/bracket_demo.py` 에서 확인할 수 있습니다.
