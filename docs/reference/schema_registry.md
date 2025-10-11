# Schema Registry

QMTL ships with a lightweight, in-memory schema registry client and an optional
remote HTTP client. Use `SchemaRegistryClient.from_env()` to automatically pick
the right implementation based on the `connectors.schema_registry_url` entry in
`qmtl.yml` (with `QMTL_SCHEMA_REGISTRY_URL` retained as a fallback).

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

### Validation Modes

Schema governance is controlled through validation modes:

- `canary` (default) records compatibility failures but allows the schema to
  register.
- `strict` blocks registrations that drop or mutate previously observed fields
  and raises `SchemaValidationError`.

Select the mode explicitly or via `QMTL_SCHEMA_VALIDATION_MODE`:

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

Every call to `register` produces a `SchemaValidationReport` accessible via
`client.last_validation(subject)` or by calling `client.validate(...)` directly.
When incompatibilities are detected the Prometheus counter
`seamless_schema_validation_failures_total{subject,mode}` increments so
dashboards can track regressions.

## Remote Client

Set `connectors.schema_registry_url` to enable a minimal HTTP client:

```yaml
connectors:
  schema_registry_url: "http://registry:8081"
```

Legacy deployments can continue to rely on `QMTL_SCHEMA_REGISTRY_URL` if
necessary.

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

Network errors raise `SchemaRegistryError`. A `404` is translated to `None`
when fetching a missing schema so callers can distinguish between "not found"
and fatal failures.

## Kafka Integration

`qmtl.foundation.kafka.schema_producer.SchemaAwareProducer` uses `SchemaRegistryClient.from_env()`
when a registry is not explicitly provided. This makes it easy to switch between
in-memory and remote registries via environment configuration.

