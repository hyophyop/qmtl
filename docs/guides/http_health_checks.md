# HTTP Health Check Utilities

This guide explains how to use the shared health probing helpers introduced in
`qmtl.foundation.common.health`.  They standardise the result format, error
classification, and Prometheus metrics emitted for every HTTP health probe.

## CheckResult contract

Probes return a `CheckResult` dataclass with the following fields:

| Field | Description |
| --- | --- |
| `ok` | `True` when a 2xx response was received. |
| `code` | One of `OK`, `CLIENT_ERROR`, `SERVER_ERROR`, `TIMEOUT`, `NETWORK`, or `UNKNOWN`. |
| `status` | HTTP status code when available. |
| `err` | Exception message for transport or timeout failures. |
| `latency_ms` | Wall-clock latency in milliseconds. |

Use the helper to derive a probe status:

```python
from qmtl.foundation.common.health import probe_http

result = probe_http(
    "https://service.internal/health",
    service="gateway",
    endpoint="/health",
)
if result.ok:
    logger.info("Health probe succeeded", extra=result.__dict__)
else:
    logger.warning("Health probe failed", extra=result.__dict__)
```

For asynchronous callers use `probe_http_async`, which offers the same
parameters and behaviour.

## Metrics emitted

Every probe updates the following Prometheus metrics:

- `probe_requests_total{service,endpoint,method,result}` – counter of probe
  outcomes.
- `probe_latency_seconds{service,endpoint,method}` – histogram capturing probe
  latency in seconds.
- `probe_last_ok_timestamp{service,endpoint}` – gauge storing the Unix timestamp
  of the last successful probe.

Keep label values low-cardinality by templating endpoints (for example
`/health`, `/readyz`, `/status/{team}`).  Do not pass user-supplied identifiers
or query strings through to labels.

## Testing utilities

All helpers accept an optional `metrics_registry` argument.  When provided, the
metrics are registered against that registry, which makes it easy to inspect
values in unit tests without touching the global registry.
