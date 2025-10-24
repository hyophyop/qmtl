# Prometheus 메트릭 헬퍼

Gateway와 SDK 서브시스템은 Prometheus 등록 및 리셋 보일러플레이트를 감싼 유틸리티 모듈 [`qmtl.foundation.common.metrics_factory`]({{ code_url('qmtl/foundation/common/metrics_factory.py') }}) 를 공유합니다.

## 메트릭 생성

`get_or_create_counter`, `get_or_create_gauge`, `get_or_create_histogram` 헬퍼를 사용해 메트릭을 등록하세요. 각 헬퍼는 `REGISTRY` 에 이미 등록된 수집기를 재사용해 모듈을 여러 번 임포트할 때 발생하는 ValueError를 방지합니다(테스트에서 흔함). 또한 테스트가 기대하는 `._vals` 또는 `._val` 속성을 자동으로 부착합니다.

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

`test_value_attr` 와 `test_value_factory` 파라미터는 과거 테스트가 내부 딕셔너리/리스트를 확인하던 패턴을 그대로 따라갑니다. 커스텀 저장소가 필요 없는 메트릭은 인자를 생략해도 됩니다.

## 메트릭 리셋

`metrics_factory` 는 헬퍼를 통해 생성된 모든 메트릭을 추적하며 `reset_metrics(names, registry=REGISTRY)` 로 값을 초기화합니다. SDK와 Gateway 모듈은 메트릭 이름 집합을 유지하고 자체 `reset_metrics()` 구현에서 이 헬퍼를 호출하면 됩니다. 이후 필요한 테스트 전용 정리는 별도로 진행하세요.

```python
_REGISTERED_METRICS: set[str] = set()

orders_published_total = get_or_create_counter(...)
_REGISTERED_METRICS.add("orders_published_total")


def reset_metrics() -> None:
    reset_registered_metrics(_REGISTERED_METRICS)
    _custom_test_state.clear()
```

동일한 헬퍼를 DAG Manager 등 다른 서브시스템에서도 사용할 수 있으며, `REGISTRY._names_to_collectors` 를 직접 다루지 않고도 멱등적인 메트릭 등록 semantics를 유지할 수 있습니다.
