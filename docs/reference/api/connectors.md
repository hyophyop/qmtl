---
title: "Live & Brokerage Connectors"
tags: [api]
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# Live & Brokerage Connectors

This page standardizes the SDK interfaces for connecting to live brokers and live data feeds. It complements the execution models in Brokerage API and the Gateway WS design.

Key goals:
- Provide thin, testable abstractions that are easy to adopt.
- Offer a reference connector (HTTP/CCXT) and a fake broker for demos.
- Document retry/timeout behavior and minimal configuration via YAML/env.

## BrokerageClient

```python
from qmtl.sdk import HttpBrokerageClient, FakeBrokerageClient, CcxtBrokerageClient

client = HttpBrokerageClient("https://broker/api/orders", max_retries=3, backoff=0.1)
resp = client.post_order({
    "symbol": "BTC/USDT",
    "side": "BUY",
    "type": "market",
    "quantity": 0.01,
})
```

Interface: `post_order(order)`, `poll_order_status(order)`, `cancel_order(order_id)`.

- `HttpBrokerageClient` wraps `TradeExecutionService` (HTTP POST + light retries). Status polling calls `GET {url}/{id}`, cancel attempts `DELETE {url}/{id}`.
- `FakeBrokerageClient` is an in-memory immediate-fill stub.
- `CcxtBrokerageClient` (optional) uses the CCXT unified API. Requires `ccxt` and minimal fields: `symbol`, `side` (`BUY|SELL`), `type` (`market|limit`), `quantity`, optional `limit_price` and `time_in_force`.

### Binance (CCXT Sandbox)

Binance Spot Testnet can be enabled by passing `sandbox=True` (alias `testnet=True`) to `CcxtBrokerageClient`. Provide your testnet API key/secret and use standard symbols, e.g. `BTC/USDT`.

Example:

```python
from qmtl.sdk import CcxtBrokerageClient

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

See runnable example: `qmtl/examples/brokerage_demo/ccxt_binance_sandbox_demo.py`.

### Futures (Binance USDT‑M Testnet)

Use `FuturesCcxtBrokerageClient` targeting `binanceusdm` and enable `sandbox=True`. You can optionally set `leverage`, `margin_mode` (cross/isolated), and `hedge_mode` (dual‑side) if supported.

```python
from qmtl.sdk import FuturesCcxtBrokerageClient

client = FuturesCcxtBrokerageClient(
    "binanceusdm",
    symbol="BTC/USDT",
    leverage=5,
    margin_mode="cross",
    hedge_mode=False,
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
})
```

Runnable demo: `qmtl/examples/brokerage_demo/ccxt_binance_futures_sandbox_demo.py`.

### Retry & Timeouts

- HTTP timeouts use `qmtl.sdk.runtime.HTTP_TIMEOUT_SECONDS` (2s default; 1.5s in tests).
- `TradeExecutionService` performs up to `max_retries` with `backoff` between attempts, and short-circuits if `poll_order_status` reports completion.
- For CCXT, rate limit handling is delegated to the library’s `enableRateLimit`.

## LiveDataFeed

```python
from qmtl.sdk import WebSocketFeed, FakeLiveDataFeed

async def on_msg(evt: dict) -> None:
    if evt.get("event") == "queue_update":
        ...

# real WebSocket connection
feed = WebSocketFeed("wss://gateway/ws", on_message=on_msg, token="<jwt>")
await feed.start()
...
await feed.stop()

# in‑memory testing/demos
fake = FakeLiveDataFeed(on_message=on_msg)
await fake.start()
await fake.emit({"event": "queue_update"})
await fake.stop()
```

- `WebSocketFeed` wraps SDK’s `WebSocketClient` with reconnection, heartbeat and a simple `start/stop` API.
- `FakeLiveDataFeed` is an in-memory stub that forwards messages pushed via `emit`.
- Timeouts/backoffs come from `runtime`: `WS_RECV_TIMEOUT_SECONDS` (30s default) and internal exponential backoff.

## Configuration (YAML/Env)

Minimal env configuration for a live run:

```bash
export QMTL_TRADE_MODE=live
export QMTL_BROKER_URL=https://broker/api/orders
export QMTL_TRADE_MAX_RETRIES=3
export QMTL_TRADE_BACKOFF=0.1
export QMTL_WS_URL=wss://gateway/ws
```

Example strategy: `qmtl/examples/strategies/paper_live_switch_strategy.py` reads these variables to switch between paper and live.

YAML integration: you can mirror these settings in your project config and load them before constructing clients. The SDK does not enforce a specific YAML schema.

## Usage with Runner

For live order submission via Runner’s pipeline (e.g., `TradeOrderPublisherNode`):

```python
from qmtl.sdk import Runner, TradeExecutionService

svc = TradeExecutionService("https://broker/api/orders", max_retries=3)
Runner.set_trade_execution_service(svc)
```

This routes order payloads emitted by publisher nodes to the broker. Activation gating still applies when configured.

## Error Handling Guidance

- Prefer idempotent server-side order handlers; Runner suppresses obvious client duplicates using a simple key.
- Implement server-side backoff and rate limiting; client-side retries are intentionally lightweight.
- For long-running orders, set a per-test timeout override (pytest-timeout) and poll via `poll_order_status`.

{{ nav_links() }}
