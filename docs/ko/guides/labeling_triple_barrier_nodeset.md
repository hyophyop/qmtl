# Triple-Barrier 라벨링 NodeSet 레시피

Triple-Barrier 라벨을 쉽게 생성하면서도 **학습/평가(offline)** 와 **실운용(live/paper)** 에서 **동일 NodeSet 구현**을 재사용할 수 있도록 `labeling_triple_barrier` 레시피를 제공합니다. 이 레시피는 라벨을 **delayed output stream**으로만 emit하며, 주문/의사결정 입력과 분리된 포트로 노출합니다. 자세한 누수 방지 계약은 [Labeling 계약](../design/labeling_contract.md)을 참고하세요.

## 포트 명세

- 입력 포트
  - `price`: `{"observed_time": datetime, "price": float, "symbol": str?}` 형식의 가격 관측 스트림
  - `entry_events`: `{"entry_time": datetime, "entry_price": float, "side": str, "barrier": BarrierSpec|dict, "horizon": HorizonSpec|dict}` 형식의 진입 이벤트 스트림
- 출력 포트
  - `labels`: `TripleBarrierLabel` 리스트(지연 라벨 스트림)

> 라벨은 `entry_time=t` 시점에는 생성되지 않으며, `resolved_time=t*` 이후에만 출력됩니다.
> `price` 와 `entry_events` 는 서로 다른 노드를 사용해야 합니다.

## Offline 학습/평가 예시

```python
from datetime import datetime, timedelta, timezone

from qmtl.runtime.labeling import BarrierMode, BarrierSpec, HorizonSpec
from qmtl.runtime.nodesets.recipes import make_labeling_triple_barrier_nodeset
from qmtl.runtime.sdk import StreamInput

price = StreamInput(tags=["price"], interval="1m", period=500)
entry_events = StreamInput(tags=["entry_events"], interval="1m", period=500)

nodeset = make_labeling_triple_barrier_nodeset(
    price,
    entry_events,
    world_id="train",
    barrier=BarrierSpec(
        profit_target=0.02,
        stop_loss=0.01,
        mode=BarrierMode.RETURN,
    ),
    horizon=HorizonSpec(max_bars=30),
)

# 전략 그래프에 추가
strategy.add_nodes([price, entry_events, nodeset])

# entry_events payload는 entry_time 기준으로 barrier/horizon을 동결해야 합니다.
entry_payload = {
    "entry_time": datetime.now(timezone.utc),
    "entry_price": 100.0,
    "side": "long",
    "symbol": "AAPL",
}
```

라벨 출력은 `nodeset.tail` 로 이어지며, 학습용 데이터 적재 파이프라인(예: 오프라인 피처 스토어/레이블 스토어)로 연결하세요.

## Live/Paper 운용 예시

```python
from qmtl.runtime.nodesets.recipes import make_labeling_triple_barrier_nodeset

label_nodeset = make_labeling_triple_barrier_nodeset(
    price_node,
    entry_events_node,
    world_id="live-world",
    barrier=barrier_spec,
    horizon=horizon_spec,
)

# 라벨은 모니터링/리포팅/사후 학습 데이터 적재용 스트림으로만 사용
monitoring_sink.add_input(label_nodeset.tail)
```

> 라벨 출력은 주문/의사결정 경로에 연결하지 마세요. 동일 NodeSet을 사용하되 출력 스트림을 분리해 누수를 방지합니다.
