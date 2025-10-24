# 스키마 레지스트리

QMTL에는 경량 인메모리 스키마 레지스트리 클라이언트와 선택적 원격 HTTP 클라이언트가 포함되어 있습니다. `SchemaRegistryClient.from_env()` 를 사용하면 `qmtl.yml` 의 `connectors.schema_registry_url` 값(필요 시 `QMTL_SCHEMA_REGISTRY_URL` 폴백)을 기준으로 적절한 구현을 자동 선택합니다.

## 인메모리 클라이언트

기본 `SchemaRegistryClient` 는 프로세스 내에 스키마를 저장하고 주제(subject)별 증가하는 ID/버전을 부여합니다.

```python
from qmtl.foundation.schema import SchemaRegistryClient

reg = SchemaRegistryClient()
sch1 = reg.register("prices", '{"a": 1}')
assert reg.latest("prices").id == sch1.id
sch2 = reg.register("prices", '{"a": 1, "b": 2}')
assert sch2.version == 2
```

`get_by_id(id: int)` 는 전역 ID로 스키마를 조회합니다.

### 검증 모드

스키마 거버넌스는 검증 모드로 제어됩니다.

- `canary`(기본값): 호환성 실패를 기록하지만 등록은 허용.
- `strict`: 기존 필드 제거/변경이 감지되면 등록을 차단하고 `SchemaValidationError` 를 발생.

모드는 명시적으로 지정하거나 `QMTL_SCHEMA_VALIDATION_MODE` 환경 변수로 설정할 수 있습니다.

```python
from qmtl.foundation.schema import (
    SchemaRegistryClient,
    SchemaValidationError,
    SchemaValidationMode,
)

reg = SchemaRegistryClient(validation_mode=SchemaValidationMode.STRICT)
reg.register("prices", '{"a": 1, "b": 2}')

try:
    reg.register("prices", '{"a": 1}')
except SchemaValidationError as exc:
    print("strict mode blocked change", exc)
```

`register` 호출마다 `SchemaValidationReport` 가 생성되며 `client.last_validation(subject)` 또는 `client.validate(...)` 로 확인할 수 있습니다. 호환성 문제가 발생하면 Prometheus 카운터 `seamless_schema_validation_failures_total{subject,mode}` 가 증가해 대시보드에서 회귀를 추적할 수 있습니다.

## 원격 클라이언트

`connectors.schema_registry_url` 을 설정하면 최소한의 HTTP 클라이언트를 사용할 수 있습니다.

```yaml
connectors:
  schema_registry_url: "http://registry:8081"
```

레거시 배포는 필요 시 `QMTL_SCHEMA_REGISTRY_URL` 환경 변수를 계속 사용할 수 있습니다.

```python
from qmtl.foundation.schema import SchemaRegistryClient

reg = SchemaRegistryClient.from_env()  # RemoteSchemaRegistryClient 반환
reg.register("prices", '{"a": 1}')
latest = reg.latest("prices")
by_id = reg.get_by_id(latest.id)
```

예상되는 JSON API는 일반 레지스트리 엔드포인트와 유사합니다.

- `POST /subjects/{subject}/versions` → `{ "id": <int> }`
- `GET /subjects/{subject}/versions/latest` → `{ "id": <int>, "schema": <str>, "version": <int> }`
- `GET /schemas/ids/{id}` → `{ "schema": <str> }`

네트워크 오류는 `SchemaRegistryError` 로 래핑되고, 스키마 조회 시 `404` 는 `None` 으로 변환되어 호출자가 “없음(not found)”과 치명적 실패를 구분할 수 있습니다.

## Kafka 통합

`qmtl.foundation.kafka.schema_producer.SchemaAwareProducer` 는 명시적으로 레지스트리를 전달하지 않으면 `SchemaRegistryClient.from_env()` 를 사용합니다. 이를 통해 환경 설정만으로 인메모리와 원격 레지스트리 간 전환이 가능합니다.
