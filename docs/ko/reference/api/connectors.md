---
title: "라이브 및 브로커리지 커넥터"
tags: [api]
author: "QMTL Team"
last_modified: 2025-09-22
---

{{ nav_links() }}

# 라이브 및 브로커리지 커넥터

이 문서는 라이브 브로커와 데이터 피드에 연결하기 위한 SDK 인터페이스를 표준화합니다. 브로커리지 API의 실행 모델과 Gateway WebSocket 설계를 보완하며, CCXT 메타데이터로 수수료 모델을 구성하는 방법은 브로커리지 API의 `make_ccxt_brokerage()` 를 참고하세요.

핵심 목표:
- 채택하기 쉬운 얇고 테스트 가능한 추상화를 제공
- 레퍼런스 커넥터(HTTP/CCXT)와 데모용 페이크 브로커 제공
- 재시도/타임아웃 동작과 최소 구성(YAML/env)을 문서화

## BrokerageClient

```python
from qmtl.runtime.sdk import HttpBrokerageClient, FakeBrokerageClient, CcxtBrokerageClient

client = HttpBrokerageClient("https://broker/api/orders", max_retries=3, backoff=0.1)
resp = client.post_order({
    "symbol": "BTC/USDT",
    "side": "BUY",
    "type": "market",
    "quantity": 0.01,
})
```

인터페이스: `post_order(order)`, `poll_order_status(order)`, `cancel_order(order_id)`.

- `HttpBrokerageClient` 는 `TradeExecutionService` 를 감싸며 HTTP POST 후 가벼운 재시도를 수행합니다. 상태 폴링은 `GET {url}/{id}` 를 호출하고, 취소는 `DELETE {url}/{id}` 를 시도합니다.
- `FakeBrokerageClient` 는 메모리 기반 즉시 체결 스텁입니다.
- `CcxtBrokerageClient` (선택)은 CCXT 통합 API를 사용합니다. 필수 필드는 `symbol`, `side` (`BUY|SELL`), `type` (`market|limit`), `quantity` 이며, `limit_price`, `time_in_force` 는 선택입니다.

### OCO(상호 취소 주문)

일부 전략은 익절/손절 주문을 연동된 OCO 쌍으로 관리해야 합니다.

| 커넥터 | OCO 지원 |
| --- | --- |
| `FakeBrokerageClient` | 체결 시 서로 취소를 에뮬레이션 |
| `HttpBrokerageClient` | 수동 취소 필요 |
| `CcxtBrokerageClient` | 거래소에 따라 다름 |

### 바이낸스(CCXT 샌드박스)

Binance Spot Testnet은 `CcxtBrokerageClient` 에 `sandbox=True` (또는 `testnet=True`) 를 지정하면 사용할 수 있습니다. 테스트넷 API 키/시크릿을 제공하고, `BTC/USDT` 와 같은 표준 심볼을 사용하세요.

```python
from qmtl.runtime.sdk import CcxtBrokerageClient

client = CcxtBrokerageClient(
    "binance",
    apiKey="<TESTNET_KEY>",
    secret="<TESTNET_SECRET>",
    sandbox=True,
    options={"defaultType": "spot"},
)

resp = client.post_order({
    "symbol": "BTC/USDT",
    "side": "BUY",
    "type": "limit",
    "quantity": 0.001,
    "limit_price": 10000.0,
    "time_in_force": "GTC",
})
```

실행 예제: `qmtl/examples/brokerage_demo/ccxt_binance_sandbox_demo.py`.

### 선물(Binance USDT-M Testnet)

`FuturesCcxtBrokerageClient` 를 사용해 `binanceusdm` 을 대상으로 하고 `sandbox=True` 를 설정하세요. 필요 시 `leverage`, `margin_mode` (교차/격리), `hedge_mode` (듀얼 사이드)를 지정할 수 있습니다. 지원되는 거래소에서는 주문별 레버리지 변경도 적용할 수 있습니다.

```python
from qmtl.runtime.sdk import FuturesCcxtBrokerageClient

client = FuturesCcxtBrokerageClient(
    "binanceusdm",
    symbol="BTC/USDT",
    leverage=5,
    margin_mode="cross",
    hedge_mode=True,
    apiKey="<TESTNET_KEY>",
    secret="<TESTNET_SECRET>",
    sandbox=True,
)

resp = client.post_order({
    "symbol": "BTC/USDT",
    "side": "BUY",
    "type": "limit",
    "quantity": 0.001,
    "limit_price": 10000.0,
    "time_in_force": "GTC",
    "reduce_only": False,
    "position_side": "LONG",  # hedge_mode=True 필요
    "leverage": 10,
})
```

데모: `qmtl/examples/brokerage_demo/ccxt_binance_futures_sandbox_demo.py`.

### 재시도 & 타임아웃

- HTTP 타임아웃은 `qmtl.runtime.sdk.runtime.HTTP_TIMEOUT_SECONDS` (기본 2초, 테스트 1.5초)를 사용합니다.
- `TradeExecutionService` 는 최대 `max_retries` 만큼 시도하면서 `backoff` 초 간격으로 재시도하며, `poll_order_status` 가 완료를 보고하면 즉시 종료합니다.
- CCXT 는 라이브러리의 `enableRateLimit` 설정을 활용해 레이트 리밋을 처리합니다.

## LiveDataFeed

```python
from qmtl.runtime.sdk import WebSocketFeed, FakeLiveDataFeed

async def on_msg(evt: dict) -> None:
    if evt.get("event") == "queue_update":
        ...

# 실제 WebSocket 연결
feed = WebSocketFeed("wss://gateway/ws", on_message=on_msg, token="<jwt>")
await feed.start()
...
await feed.stop()

# 인메모리 테스트/데모
fake = FakeLiveDataFeed(on_message=on_msg)
await fake.start()
await fake.emit({"event": "queue_update"})
await fake.stop()
```

- `WebSocketFeed` 는 SDK의 `WebSocketClient` 를 감싸며 재연결, 하트비트, 간단한 `start/stop` API를 제공합니다.
- `FakeLiveDataFeed` 는 인메모리 스텁으로, `emit` 으로 푸시한 메시지를 즉시 전달합니다.
- 타임아웃/백오프는 `runtime` 모듈에서 제공하는 `WS_RECV_TIMEOUT_SECONDS` (기본 30초) 및 내부 지수 백오프를 사용합니다.

## 구성

라이브 실행을 위한 최소 `qmtl.yml` 예시는 다음과 같습니다.

```yaml
connectors:
  execution_domain: live
  broker_url: https://broker/api/orders
  trade_max_retries: 3
  trade_backoff: 0.1
  ws_url: wss://gateway/ws
```

예시 전략 `qmtl/examples/strategies/dryrun_live_switch_strategy.py` 는 이 설정을 읽어 브로커/WebSocket 연계를 선택적으로 구성합니다.

## Runner 에서의 사용

Runner 파이프라인(예: `TradeOrderPublisherNode`)에서 라이브 주문을 전송하려면:

```python
from qmtl.runtime.sdk import Runner, TradeExecutionService

svc = TradeExecutionService("https://broker/api/orders", max_retries=3)
Runner.set_trade_execution_service(svc)
```

이렇게 하면 퍼블리셔 노드가 내보낸 주문 페이로드가 브로커로 라우팅됩니다. 구성된 경우 활성화 게이트는 그대로 적용됩니다.

## 오류 처리 가이드

- 서버 측 주문 핸들러는 가능한 멱등하게 구현하세요. Runner는 간단한 키로 클라이언트 중복을 억제합니다.
- 서버 측 백오프와 레이트 리밋을 구현하는 것이 좋습니다. 클라이언트 재시도는 가볍게 유지되어 있습니다.
- 장시간 실행되는 주문은 테스트별 타임아웃(pytest-timeout)을 지정하고 `poll_order_status` 로 상태를 확인하세요.

{{ nav_links() }}
