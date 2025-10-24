# Gateway Fills Webhook

Gateway는 브로커 또는 실행기가 체결/취소 이벤트를 제출할 수 있는 HTTP 엔드포인트를 제공합니다. 허용된 이벤트는 검증 후 Kafka 토픽 `trade.fills` 로 전달됩니다.

## 엔드포인트

`POST /fills`

## 인증

다음 중 하나를 제공하세요.

- `Authorization: Bearer <jwt>` – 공유 이벤트 시크릿으로 서명한 JWT입니다. 토큰에는 `aud="fills"` 가 포함되어야 하며 `world_id`, `strategy_id` 클레임이 페이로드와 일치해야 합니다.
- `X-Signature` – 요청 본문을 `QMTL_FILL_SECRET` 으로 HMAC-SHA256 서명한 값입니다. 월드와 전략은 `X-World-ID`, `X-Strategy-ID` 헤더로 전달할 수 있습니다.

## 페이로드

요청 본문은 [ExecutionFillEvent](order_events.md) 스키마를 따라야 합니다. 알 수 없는 필드는 무시됩니다.

예시:

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

## 실패 처리

- `400` – JSON이 잘못되었거나 스키마 검증에 실패했습니다.
- `401` – 인증 실패 또는 누락입니다.
- `202` – 이벤트가 승인되어 Kafka로 전달되었습니다.

생성된 Kafka 메시지는 키 `world_id|strategy_id|symbol|order_id` 를 사용하며, 런타임 지문은 Kafka 헤더에 포함됩니다.
