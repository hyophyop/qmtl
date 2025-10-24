# Node Set 포트폴리오 스코프

이 가이드는 동일 월드 내 여러 전략이 포트폴리오 상태를 공유하도록 Node Set을 구성하는 방법(월드 스코프)과 전략별로 고립시키는 방법(전략 스코프)을 설명합니다.

엔드투엔드 설계는 [거래소 Node Set](../architecture/exchange_node_sets.md) 문서를 참고하세요.

## 사용 예시

```python
from qmtl.runtime.nodesets.base import NodeSetBuilder
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.sdk import Strategy, StreamInput, Node
from qmtl.runtime.transforms import TradeSignalGeneratorNode


class WorldScopeNodeSetStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(interval="60s", period=2)

        def compute_alpha(view):
            data = view[price][price.interval]
            if len(data) < 2:
                return 0.0
            prev = data[-2][1]["close"]
            last = data[-1][1]["close"]
            return (last - prev) / prev

        alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
        signal = TradeSignalGeneratorNode(
            alpha, long_threshold=0.0, short_threshold=0.0, size=1.0
        )

        # 월드 스코프는 동일 월드 내 전략 간 포트폴리오를 공유합니다.
        opts = NodeSetOptions(portfolio_scope="world")
        nodeset = NodeSetBuilder(options=opts).attach(signal, world_id="demo", scope="world")

        # 시그널 뒤에 있는 실행 체인을 단일 단위로 추가합니다.
        self.add_nodes([price, alpha, signal, *nodeset])
```

메모
- `strategy` 스코프(기본값)는 포트폴리오 스냅샷과 체결을 `(world_id, strategy_id, symbol)` 기준으로 분리합니다.
- `world` 스코프는 `(world_id, symbol)` 로 묶어 동일 월드 내 여러 전략이 현금/한도를 공유합니다.
- Node Set은 블랙박스로 취급하세요. attach → add 방식이 권장되며 내부 노드는 구현 세부사항으로 변경될 수 있습니다.
- 내장 Node Set 레시피와 기본 빌더는 `portfolio_scope="world"` 설정 시 월드별 `Portfolio` 인스턴스를 공유해 동일 월드 전략이 동일한 현금/포지션 뷰를 자동으로 사용합니다.
