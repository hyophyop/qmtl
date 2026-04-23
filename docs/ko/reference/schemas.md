---
title: "스키마 — Decision/Activation & Events"
tags: [reference, schemas]
author: "QMTL Team"
last_modified: 2026-03-06
---

{{ nav_links() }}

# 스키마 — Decision/Activation & Events

- DecisionEnvelope: reference/schemas/decision_envelope.schema.json
- ActivationEnvelope: reference/schemas/activation_envelope.schema.json
- ActivationUpdated 이벤트: reference/schemas/event_activation_updated.schema.json
- QueueUpdated 이벤트: reference/schemas/event_queue_updated.schema.json
- QueueLifecycle 이벤트: reference/schemas/event_queue_lifecycle.schema.json
- PolicyUpdated 이벤트: reference/schemas/event_policy_updated.schema.json
- 노드(GSG): reference/schemas/node.schema.json
- 월드: reference/schemas/world.schema.json
- WorldNodeRef(WVG): reference/schemas/world_node_ref.schema.json
- Validation(WVG): reference/schemas/validation.schema.json
- DecisionsRequest(WVG): reference/schemas/decisions_request.schema.json
- OrderPayload: reference/schemas/order_payload.schema.json
- OrderAck: reference/schemas/order_ack.schema.json
- ExecutionFillEvent: reference/schemas/execution_fill_event.schema.json
- PortfolioSnapshot: reference/schemas/portfolio_snapshot.schema.json

## 노드 I/O 스키마

표준 DataFrame 계약은 노드 간 일관된 컬럼, dtype, 타임존 처리를 보장합니다. 모든 스키마는 UTC 타임존의 ``ts`` 컬럼을 요구합니다.

| 스키마 | 컬럼 |
| ------ | ----- |
| ``bar`` | ``ts`` (UTC ``Datetime(time_unit='ns', time_zone='UTC')``), ``open`` ``Float64``, ``high`` ``Float64``, ``low`` ``Float64``, ``close`` ``Float64``, ``volume`` ``Float64`` |
| ``quote`` | ``ts`` (UTC ``Datetime(time_unit='ns', time_zone='UTC')``), ``bid`` ``Float64``, ``ask`` ``Float64``, ``bid_size`` ``Float64``, ``ask_size`` ``Float64`` |
| ``trade`` | ``ts`` (UTC ``Datetime(time_unit='ns', time_zone='UTC')``), ``price`` ``Float64``, ``size`` ``Float64`` |

예시:

```python
import polars as pl
from qmtl.foundation.schema import validate_schema

df = pl.DataFrame(
    {
        "ts": pl.datetime_range(
            "2024-01-01",
            "2024-01-01",
            interval="1d",
            eager=True,
            time_unit="ns",
            time_zone="UTC",
        ),
        "open": [1.0],
        "high": [1.0],
        "low": [1.0],
        "close": [1.0],
        "volume": [1.0],
    }
)

validate_schema(df, "bar")
```

## 레지스트리 통합(선택)

`qmtl.yml` 의 `connectors.schema_registry_url`(또는 레거시 `QMTL_SCHEMA_REGISTRY_URL`)을 설정하면 외부 스키마 레지스트리를 통해 `schema_id` 를 해석할 수 있습니다. `qmtl/foundation/schema/registry.py` 에 경량 인메모리 클라이언트가 제공되며, 프로덕션 배포에서는 Confluent 또는 Redpanda 클라이언트로 교체할 수 있습니다.

## ControlBus 이벤트 인코딩

Gateway의 공개 ControlBus 계약은 JSON 전용입니다. 이벤트는 UTF-8 JSON
객체로 교환되며, 공개 스키마 표면에는 CloudEvents-over-Protobuf 변형이나
`application/cloudevents+proto` 기반 콘텐츠 협상 경로가 포함되지 않습니다.

{{ nav_links() }}
