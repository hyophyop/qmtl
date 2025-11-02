---
title: "스키마 — Decision/Activation & Events"
tags: [reference, schemas]
author: "QMTL Team"
last_modified: 2025-08-29
---

{{ nav_links() }}

# 스키마 — Decision/Activation & Events

- DecisionEnvelope: reference/schemas/decision_envelope.schema.json
- ActivationEnvelope: reference/schemas/activation_envelope.schema.json
- ActivationUpdated 이벤트: reference/schemas/event_activation_updated.schema.json
- QueueUpdated 이벤트: reference/schemas/event_queue_updated.schema.json
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
| ``bar`` | ``ts`` (UTC ``datetime64[ns]``), ``open`` ``float64``, ``high`` ``float64``, ``low`` ``float64``, ``close`` ``float64``, ``volume`` ``float64`` |
| ``quote`` | ``ts`` (UTC ``datetime64[ns]``), ``bid`` ``float64``, ``ask`` ``float64``, ``bid_size`` ``float64``, ``ask_size`` ``float64`` |
| ``trade`` | ``ts`` (UTC ``datetime64[ns]``), ``price`` ``float64``, ``size`` ``float64`` |

예시:

```python
import pandas as pd
from qmtl.foundation.schema import validate_schema

df = pd.DataFrame(
    {
        "ts": pd.date_range("2024-01-01", periods=1, tz="UTC"),
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

## ControlBus CloudEvents — Protobuf 마이그레이션 경로

ControlBus는 현재 JSON을 지원합니다. `qmtl/services/gateway/controlbus_codec.py` 에 있는 플레이스홀더 코덱을 통해 CloudEvents-over-Protobuf 마이그레이션 경로가 제공되며, `content_type=application/cloudevents+proto` 헤더를 첨부하면서 호환성을 위해 JSON 페이로드를 유지합니다. 소비자는 헤더 기반 라우팅과 디코딩을 수행하고, 모든 소비자가 새 헤더를 인식할 때까지 듀얼 퍼블리싱으로 롤아웃할 수 있습니다.

{{ nav_links() }}
