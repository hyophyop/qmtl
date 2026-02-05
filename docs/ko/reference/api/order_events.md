---
title: "주문 및 체결 이벤트 스키마"
tags: [api, events]
author: "QMTL Team"
last_modified: 2026-02-05
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

### CloudEvents 엔벌로프

Gateway `/fills` Webhook 요청 본문은 CloudEvents 1.0 엔벌로프여야 합니다. 최소 `specversion` 과 객체 형태의 `data` 필드가 필요합니다.

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

`data` 객체는 `ExecutionFillEvent` 스키마를 따라야 하며, 순수 `ExecutionFillEvent` JSON 본문은 허용되지 않습니다. 엔벌로프가 없거나 `data` 가 객체가 아니면 `400 E_CE_REQUIRED` 를 반환합니다.

CloudEvents 최상위 필드 중 `id`, `type`, `source`, `time` 이 문자열이면 Kafka 헤더(`ce_id`, `ce_type`, `ce_source`, `ce_time`)로 전달됩니다.

## Gateway `/fills` Webhook

Gateway는 브로커 콜백을 위한 `/fills` 엔드포인트를 제공합니다. 인증과 스코프 식별은 다음 규칙을 따릅니다.

- `Authorization: Bearer <jwt>` 헤더가 있으면 JWT 경로를 사용합니다. 토큰은 공유 이벤트 키로 서명되어야 하며 `aud="fills"` 와 `world_id`, `strategy_id` 클레임이 필요합니다.
- Bearer 헤더가 없을 때만 `X-Signature` 대체 경로를 사용합니다. `X-Signature` 는 원본 요청 본문(raw bytes)의 HMAC-SHA256 hex digest 여야 하며 `QMTL_FILL_SECRET` 설정이 필요합니다.
- HMAC 경로에서 `world_id`, `strategy_id` 는 `X-World-ID`, `X-Strategy-ID` 헤더를 우선 사용하고, 헤더가 없으면 CloudEvents 최상위 확장 필드(`world_id`, `strategy_id`)를 사용합니다.
- 인증 정보가 없거나 검증에 실패하면 `401 E_AUTH`, 스코프 식별자(`world_id`, `strategy_id`)를 결정할 수 없으면 `400 E_MISSING_IDS` 를 반환합니다.

### 재전송 엔드포인트

현재 Gateway 구현은 `GET /fills/replay` placeholder 엔드포인트만 제공하며, 실제 재전송은 아직 구현되지 않았습니다. 요청 시 `202 Accepted`와 함께 `"replay not implemented in this build"` 메시지가 반환됩니다.

{{ nav_links() }}
