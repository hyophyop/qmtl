{{ nav_links() }}

# SDK 사용 가이드

본 문서는 QMTL SDK를 이용해 전략을 구현하고 실행하는 기본 절차를 소개합니다. 보다 상세한 아키텍처 설명과 예시는 [architecture.md](../architecture/architecture.md)와 `qmtl/examples/` 디렉터리를 참고하세요.

## 설치

```bash
uv venv
uv pip install -e .[dev]
```

필요에 따라 데이터 IO 모듈을 설치할 수 있습니다.

```bash
uv pip install -e .[io]  # 데이터 IO 모듈
```

## 기본 구조


SDK를 사용하려면 `Strategy` 클래스를 상속하고 `setup()` 메서드만 구현하면 됩니다. 노드는 `StreamInput`, `TagQueryNode` 와 같은 **소스 노드**(`SourceNode`)와 다른 노드를 처리하는 **프로세싱 노드**(`ProcessingNode`)로 나뉩니다. `ProcessingNode`는 하나 이상의 업스트림을 반드시 가져야 합니다. `interval` 값은 정수 또는 `"1h"`, `"30m"`, `"45s"`처럼 단위 접미사를 가진 문자열로 지정할 수 있습니다. `period` 값은 **항상 양의 정수(바 개수)** 로 지정합니다. `TagQueryNode` 자체는 네트워크 요청을 수행하지 않고, Runner가 생성하는 **TagQueryManager**가 Gateway와 통신하여 큐 목록을 갱신합니다. 각 노드가 등록된 후 `TagQueryManager.resolve_tags()`를 호출하여 초기 큐 목록을 받아오며, 이후 업데이트는 WebSocket을 통해 처리됩니다. 태그 매칭 방식은 `match_mode` 옵션으로 지정하며 기본값은 OR 조건에 해당하는 `"any"` 입니다. 모든 태그가 일치해야 할 경우 `match_mode="all"`을 사용합니다.

### WebSocketClient

Gateway 상태 변화를 실시간으로 수신하기 위한 클래스입니다. 기본 사용법은 다음과 같습니다.

```python
client = WebSocketClient("ws://localhost:8000/ws", on_message=my_handler)
```

`url`은 WebSocket 엔드포인트 주소이며 `on_message`는 수신 메시지를 처리할 비동기 함수입니다. `start()`를 호출하면 백그라운드에서 연결을 유지하며 메시지를 받고, `stop()`을 호출하면 연결이 종료됩니다.

`TagQueryManager`는 이 객체를 생성하거나 주입받아 `handle_message()`를 콜백으로 등록합니다. 큐 업데이트(`queue_update`)와 센티널 가중치(`sentinel_weight`) 이벤트가 도착하면 해당 `TagQueryNode`에 `update_queues()`가 호출되고, 가중치 값은 `WebSocketClient.sentinel_weights`에 저장됩니다.


`ProcessingNode`의 `input`은 단일 노드 또는 노드들의 리스트로 지정합니다. 딕셔너리 입력 형식은 더 이상 지원되지 않습니다.

### Node와 ProcessingNode

`Node`는 모든 노드의 기본 클래스이며, 특별한 제약이 없습니다. 반면 `ProcessingNode`는 한 개 이상의 업스트림 노드를 요구하도록 만들어져 있어 연산 노드를 구현할 때 보다 명시적인 오류 메시지를 제공합니다. 새로운 프로세싱 로직을 구현할 때는 `ProcessingNode`를 상속하는 방식을 권장합니다. 필요하지 않은 경우에는 기본 `Node`만 사용해도 동작에는 문제가 없습니다.


```python
from qmtl.sdk import Strategy, ProcessingNode, StreamInput

class MyStrategy(Strategy):
    def setup(self):
        price = StreamInput(interval="1m", period=30)

        def compute(view):
            return view

        out = ProcessingNode(input=price, compute_fn=compute, name="out")
        self.add_nodes([price, out])
```

## 실행 모드

전략은 `Runner` 클래스로 실행합니다. 모드는 `backtest`, `dryrun`, `live`, `offline` 네 가지가 있으며 CLI 또는 Python 코드에서 선택할 수 있습니다. 각 모드의 의미는 다음과 같습니다.

- **backtest**: 과거 데이터를 재생하며 전략을 검증합니다. Gateway에 DAG을 전송하여 큐 매핑을 받아오므로 `--gateway-url`이 필수입니다.
- **dryrun**: Gateway와 통신하지만 실거래는 하지 않습니다. 연결 상태와 태그 매핑을 점검할 때 사용하며 역시 `--gateway-url`을 지정해야 합니다.
- **live**: 실시간 거래 모드로 Gateway 및 외부 서비스와 연동됩니다. 반드시 `--gateway-url`을 지정해야 합니다.
- **offline**: Gateway 없이 로컬에서만 실행합니다. 태그 기반 노드는 빈 큐 목록으로 초기화되며, 게이트웨이 연결이 없음을 가정한 테스트용입니다.

```bash
# 커맨드라인 예시
python -m qmtl.sdk tests.sample_strategy:SampleStrategy --mode backtest --start-time 2024-01-01 --end-time 2024-02-01 --gateway-url http://gw
python -m qmtl.sdk tests.sample_strategy:SampleStrategy --mode offline
```

```python
from qmtl.sdk import Runner
Runner.dryrun(MyStrategy, gateway_url="http://gw")
```

과거 데이터를 재생하려면 `Runner.backtest()`에 시작 및 종료 시점을 전달합니다.

```python
from qmtl.sdk import Runner
Runner.backtest(
    MyStrategy,
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-02-01T00:00:00Z",
    gateway_url="http://gw",
)
```

`Runner`를 사용하면 각 `TagQueryNode`가 등록된 후 자동으로 Gateway와 통신하여
해당 태그에 매칭되는 큐를 조회하고 WebSocket 구독을 시작합니다. 백테스트와 dry-run 모드에서도 Gateway URL을 지정하지 않으면 `RuntimeError`가 발생합니다.

## CLI 도움말

CLI에 대한 전체 옵션은 다음 명령으로 확인할 수 있습니다.

```bash
python -m qmtl.sdk --help
```

## 캐시 조회

`compute_fn`에는 `NodeCache.view()`가 반환하는 **읽기 전용 CacheView** 객체가
전달됩니다. 이전 버전에서 사용하던 `NodeCache.snapshot()`은 내부 구현으로
변경되었으므로 전략 코드에서 직접 호출하지 않아야 합니다.

PyArrow 기반 캐시를 사용하려면 환경 변수 `QMTL_ARROW_CACHE=1`을 설정합니다.
만료 슬라이스 정리는 `QMTL_CACHE_EVICT_INTERVAL`(초) 값에 따라 주기적으로 실행되며
Ray가 설치되어 있으면 Ray Actor에서 동작합니다. CLI의 `--no-ray` 옵션을 사용하면 계산 함수 실행과
캐시 정리가 모두 스레드 기반으로 전환됩니다.

## Cache Backends

기본 `NodeCache`는 각 `(upstream_id, interval)` 쌍을 링 버퍼로 관리합니다. 누락된
타임스탬프는 `missing_flags()`로 확인하고 마지막 버킷은 `last_timestamps()`로 조회할
수 있습니다. `get_slice()`는 리스트 또는 `xarray.DataArray` 형태의 윈도우 데이터를
반환합니다.

PyArrow가 설치되어 있고 `QMTL_ARROW_CACHE=1`을 설정하면 `NodeCacheArrow` 백엔드가
활성화됩니다. 만료된 슬라이스는 `QMTL_CACHE_EVICT_INTERVAL` 초 간격으로 제거되며
Ray가 켜져 있고 `--no-ray`를 사용하지 않는 경우 Actor에서, 그렇지 않으면 백그라운드 스레드에서 실행됩니다.

캐시 조회 수는 `qmtl.sdk.metrics` 모듈의 `cache_read_total` 및
`cache_last_read_timestamp` 지표로 모니터링할 수 있습니다. 다음과 같이 메트릭 서버를
시작하면 `/metrics` 경로에서 값을 확인할 수 있습니다.

```python
from qmtl.sdk import metrics

metrics.start_metrics_server(port=8000)
```

## Performance Metrics

`alpha_performance_node`는 Sharpe, 최대 낙폭, CAR/MDD 등의 성과 지표를 계산합니다.
`alpha_history_node`와 조합하면 수익률 누적과 성과 계산을 분리하여 로직과 테스트를
병렬로 개발할 수 있습니다.

```python
from qmtl.transforms import alpha_history_node, alpha_performance_from_history_node

history = alpha_history_node(alpha, window=30)
perf = alpha_performance_from_history_node(history)
```

## Custom Alpha Indicators with History

`alpha_indicator_with_history` wraps a function that returns an
``{"alpha": value}`` mapping and automatically maintains a sliding
window of recent alpha values:

```python
from qmtl.indicators import alpha_indicator_with_history

history = alpha_indicator_with_history(my_alpha_fn, inputs=[src], window=30)
```

## Alpha-to-Signal Pipeline

`TradeSignalGeneratorNode` converts an alpha history into actionable trade
signals. Combine it with `alpha_history_node` to produce orders based on the
latest alpha value:

```python
from qmtl.transforms import TradeSignalGeneratorNode

history = alpha_history_node(alpha, window=30)
signal = TradeSignalGeneratorNode(
    history,
    long_threshold=0.5,
    short_threshold=-0.5,
)
```

## ExecutionModel과 비용 조정 성과 지표

`ExecutionModel`은 커미션, 슬리피지, 시장 임팩트 등 현실적인 체결 비용을 추정합니다.
생성된 `ExecutionFill` 목록을 `alpha_performance_node`에 전달하면 비용을 반영한 성과 지표를 계산할 수 있습니다.

```python
from qmtl.sdk.execution_modeling import (
    ExecutionModel, OrderSide, OrderType, create_market_data_from_ohlcv,
)
from qmtl.transforms import TradeSignalGeneratorNode, alpha_history_node
from qmtl.transforms.alpha_performance import alpha_performance_node

history = alpha_history_node(alpha, window=30)
signal = TradeSignalGeneratorNode(history, long_threshold=0.5, short_threshold=-0.5)

model = ExecutionModel(commission_rate=0.0005, base_slippage_bps=2.0)
market = create_market_data_from_ohlcv(
    timestamp=0,
    open_price=100,
    high=101,
    low=99,
    close=100,
    volume=10_000,
)

fill = model.simulate_execution(
    order_id="demo",
    symbol="TEST",
    side=OrderSide.BUY,
    quantity=100,
    order_type=OrderType.MARKET,
    requested_price=100.0,
    market_data=market,
    timestamp=0,
)

metrics = alpha_performance_node(
    returns,
    execution_fills=[fill],
    use_realistic_costs=True,
)
```

## Order Results and External Executors

`TradeOrderPublisherNode` turns trade signals into standardized order
payloads. The `Runner` examines node results and delivers these orders to
external systems through a series of hooks:

1. `Runner.set_trade_execution_service(service)` forwards the order to a
   custom object exposing ``post_order``.
2. `Runner.set_trade_order_http_url(url)` posts the order to an HTTP
   endpoint as JSON.
3. `Runner.set_trade_order_kafka_topic(topic)` publishes the order to a
   Kafka topic using the configured producer.

Combine these hooks with a simple pipeline to convert alpha values into
standardized orders:

```python
from qmtl.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)

history = alpha_history_node(alpha, window=30)
signal = TradeSignalGeneratorNode(history, long_threshold=0.5, short_threshold=-0.5)
orders = TradeOrderPublisherNode(signal, topic="orders")

from qmtl.sdk import Runner, TradeExecutionService

service = TradeExecutionService("http://broker")
Runner.set_trade_execution_service(service)
Runner.set_trade_order_http_url("http://endpoint")
Runner.set_trade_order_kafka_topic("orders")
```

See [`order_pipeline_strategy.py`](../qmtl/examples/strategies/order_pipeline_strategy.py)
for a complete runnable example. If none of these targets are configured the
order is ignored, allowing strategies to remain agnostic about the actual
execution backend.

## 백필 작업

노드 캐시를 과거 데이터로 초기화하는 방법은
[backfill.md](backfill.md) 문서를 참고하세요.


{{ nav_links() }}

