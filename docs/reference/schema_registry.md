# Schema Registry

QMTL ships with a lightweight, in-memory schema registry client and an optional
remote HTTP client. Use `SchemaRegistryClient.from_env()` to automatically pick
the right implementation based on the `QMTL_SCHEMA_REGISTRY_URL` environment
variable.

## In-Memory Client

The default `SchemaRegistryClient` stores schemas in-process and assigns
incrementing ids and versions per subject.

Example:

```python
from qmtl.foundation.schema import SchemaRegistryClient

reg = SchemaRegistryClient()
sch1 = reg.register("prices", '{"a": 1}')
assert reg.latest("prices").id == sch1.id
sch2 = reg.register("prices", '{"a": 1, "b": 2}')
assert sch2.version == 2
```

`get_by_id(id: int)` looks up schemas by global id when available.

## Remote Client

Set `QMTL_SCHEMA_REGISTRY_URL` to enable a minimal HTTP client:

```bash
export QMTL_SCHEMA_REGISTRY_URL="http://registry:8081"
```

```python
from qmtl.foundation.schema import SchemaRegistryClient

reg = SchemaRegistryClient.from_env()  # returns RemoteSchemaRegistryClient
reg.register("prices", '{"a": 1}')
latest = reg.latest("prices")
by_id = reg.get_by_id(latest.id)
```

The expected JSON API is similar to common registry endpoints:

- `POST /subjects/{subject}/versions` → `{ "id": <int> }`
- `GET /subjects/{subject}/versions/latest` → `{ "id": <int>, "schema": <str>, "version": <int> }`
- `GET /schemas/ids/{id}` → `{ "schema": <str> }`

Network errors raise `RuntimeError`. Future versions may introduce a dedicated
exception type.

## Kafka Integration

`qmtl.foundation.kafka.schema_producer.SchemaAwareProducer` uses `SchemaRegistryClient.from_env()`
when a registry is not explicitly provided. This makes it easy to switch between
in-memory and remote registries via environment configuration.

