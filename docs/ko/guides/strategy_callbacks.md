# 전략 콜백

QMTL 전략은 `Strategy` 기본 클래스가 제공하는 선택적 콜백으로 라이프사이클 이벤트에 반응할 수 있습니다. 이 훅을 사용하면 DAG 노드에 명령형 로직을 넣지 않고도 상태 기반 포지션 관리를 구현할 수 있습니다.

## 제공되는 훅

- `on_start()` – 전략이 처리 흐름을 시작하기 전에 한 번 호출됩니다.
- `on_signal(signal)` – `buy_signal` 등이 생성한 트레이드 시그널 딕셔너리를 처리합니다.
- `on_fill(order, fill)` – 주문이 체결될 때 포지션 상태를 갱신합니다.
- `on_error(error)` – 복구 불가능한 오류가 발생했을 때 호출됩니다.
- `on_finish()` – 실행이 정상 종료된 후 마지막으로 호출됩니다.

## 예시

```python
from qmtl.runtime.sdk import Strategy, buy_signal

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="1m", default_period=1)
        self.in_position = False

    def on_signal(self, signal):
        if signal.get("action") == "BUY":
            self.in_position = True

    def on_fill(self, order, fill):
        self.in_position = order.get("action") == "BUY"

    def generate(self, price):
        return buy_signal(price > 0)
```
