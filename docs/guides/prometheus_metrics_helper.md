# Prometheus metric helper

The Gateway and SDK subsystems now share a small utility module,
[`qmtl.foundation.common.metrics_factory`]({{ code_url('qmtl/foundation/common/metrics_factory.py') }}), which wraps
Prometheus registration and reset boilerplate.

## Creating metrics

Use `get_or_create_counter`, `get_or_create_gauge`, or `get_or_create_histogram`
to register metrics. Each helper transparently reuses existing collectors from
`REGISTRY`, preventing the ValueError that is otherwise raised when the module is
imported multiple times (common in tests). The helpers also attach the `._vals`
or `._val` attributes expected by tests:

```python
from qmtl.foundation.common.metrics_factory import get_or_create_counter

orders_published_total = get_or_create_counter(
    "orders_published_total",
    "Total orders published by SDK",
    ["world_id"],
    test_value_attr="_vals",
    test_value_factory=dict,
)
```

The `test_value_attr` and `test_value_factory` parameters mirror the historical
pattern where tests inspect an internal dictionary/list of recorded values.
Metrics without bespoke storage can omit these arguments.

## Resetting metrics

`metrics_factory` tracks every metric constructed through the helpers and exposes
`reset_metrics(names, registry=REGISTRY)` to clear their values. The SDK and
Gateway modules simply maintain a set of metric names and call the helper in
their `reset_metrics()` implementation. Any additional test-specific cleanup
(such as clearing local deques) can follow afterwards.

```python
_REGISTERED_METRICS: set[str] = set()

orders_published_total = get_or_create_counter(...)
_REGISTERED_METRICS.add("orders_published_total")


def reset_metrics() -> None:
    reset_registered_metrics(_REGISTERED_METRICS)
    _custom_test_state.clear()
```

The same helper can be used by other subsystems (e.g. DAG Manager) to remove
manual access to `REGISTRY._names_to_collectors` while keeping idempotent metric
registration semantics.
