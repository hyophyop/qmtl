---
title: "주문 및 체결 이벤트 스키마"
tags: [api, events]
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# 주문 및 체결 이벤트 스키마

이 문서는 Exchange Node Set에서 사용하는 주문, 확인(ACK)/상태, 체결 이벤트의 최소 JSON 형태를 표준화합니다. 브로커리지 API 및 커넥터 문서와 짝을 이룹니다.

## 토픽과 키

- `trade.orders` (append-only)
  - 키: `world_id|strategy_id|symbol|client_order_id` (또는 결정적 해시)
  - 값: `OrderPayload`

- `trade.fills` (append-only)
  - 키: `world_id|strategy_id|symbol|order_id`
  - 값: `ExecutionFillEvent`

- `trade.portfolio` (compacted)
  - 키: `world_id|[strategy_id]|snapshot`
  - 값: `PortfolioSnapshot`

파티셔닝은 전략별(또는 월드별) 순서를 유지하면서 수평 확장을 허용하도록 키를 선택하세요. 스냅샷 토픽만 컴팩션을 사용합니다.

## 스키마

정식 JSON 스키마는 `reference/schemas` 폴더에 있으며, `qmtl.foundation.schema.register_order_schemas` 를 통해 프로그램적으로 등록할 수 있습니다.

OrderPayload
```json
{
  "world_id": "arch_world",
  "strategy_id": "strat_001",
  "correlation_id": "ord-20230907-0001",
  "symbol": "BTC/USDT",
  "side": "BUY",
  "type": "limit",
  "quantity": 0.01,
  "limit_price": 25000.0,
  "stop_price": null,
  "time_in_force": "GTC",
  "client_order_id": "c-abc123",
  "timestamp": 1694102400000,
  "reduce_only": false,
  "position_side": null,
  "metadata": {"source": "node_set/binance_spot"}
}
```

OrderAck / Status
```json
{
  "order_id": "exch-7890",
  "client_order_id": "c-abc123",
  "status": "accepted",
  "reason": null,
  "broker": "binance",
  "raw": {"provider_payload": "..."}
}
```

ExecutionFillEvent
```json
{
  "order_id": "exch-7890",
  "client_order_id": "c-abc123",
  "correlation_id": "ord-20230907-0001",
  "symbol": "BTC/USDT",
  "side": "BUY",
  "quantity": 0.005,
  "price": 24990.5,
  "commission": 0.02,
  "slippage": 0.5,
  "market_impact": 0.0,
  "tif": "GTC",
  "fill_time": 1694102401100,
  "status": "partially_filled",
  "seq": 12,
  "etag": "w1-s1-7890-12"
}
```

PortfolioSnapshot (compacted)
```json
{
  "world_id": "arch_world",
  "strategy_id": "strat_001",
  "as_of": 1694102402000,
  "cash": 100000.0,
  "positions": {
    "BTC/USDT": {"qty": 0.01, "avg_cost": 25010.0, "mark": 24995.0}
  },
  "metrics": {"exposure": 0.25, "leverage": 1.1}
}
```

## 참고 사항

- 타임 인 포스 의미는 실행 상태 문서와 동일합니다.
- `client_order_id` 는 선택이지만 멱등성과 조정을 위해 권장됩니다.
- 프로바이더는 `metadata` 또는 `raw` 에 필드를 추가할 수 있으며, 다운스트림 컨슈머는 알 수 없는 키를 무시해야 합니다.

### CloudEvents 엔벌로프(선택)

Webhook 및 내부 이벤트 전송은 CloudEvents 1.0으로 페이로드를 감쌀 수 있습니다.

```json
{
  "specversion": "1.0",
  "type": "qmtl.trade.fill",
  "source": "broker/binanceusdm",
  "id": "exch-7890-12",
  "time": "2025-09-08T00:00:01.100Z",
  "datacontenttype": "application/json",
  "data": { /* ExecutionFillEvent */ }
}
```

소비자는 순수 JSON과 CloudEvents 래핑된 형태 모두를 허용해야 합니다.

## Gateway `/fills` Webhook

Gateway는 브로커 콜백을 위한 `/fills` 엔드포인트를 제공합니다. 페이로드는 순수 `ExecutionFillEvent` 또는 CloudEvents 1.0 엔벌로프 형태로 전송할 수 있습니다. 요청에는 HMAC 서명된 JWT가 포함되어야 하며 `world_id`, `strategy_id` 클레임이 페이로드와 일치해야 합니다. 범위를 벗어난 요청은 거절됩니다.

### 재전송 엔드포인트

현재 Gateway 구현은 `GET /fills/replay` placeholder 엔드포인트만 제공하며, 실제 재전송은 아직 구현되지 않았습니다. 요청 시 `202 Accepted`와 함께 `"replay not implemented in this build"` 메시지가 반환됩니다.

{{ nav_links() }}
