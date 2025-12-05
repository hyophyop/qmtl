---
title: "모니터링 및 알림"
tags: []
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# 모니터링 및 알림

이 문서는 QMTL 서비스에 대한 Prometheus 경보와 Grafana 대시보드 예시를 설명합니다.

Core Loop 경로 전반의 골든 시그널과 권장 SLO/대시보드는 [core_loop_golden_signals.md](core_loop_golden_signals.md)에서 묶어 관리합니다. 이 문서는 개별 서비스 지표와 배포 방법을 다룹니다.

## 알림 규칙(Alert Rules)

Prometheus는 `alert_rules.yml`을 로드해 DAG Manager와 Gateway용 경보를 활성화할 수 있습니다. 저장소에는 핵심 경보 몇 가지가 포함된 최소 예제가 제공됩니다. 이 파일을 Prometheus 컨테이너에 마운트하고 필요에 따라 확장하세요.

### 추가 알림 참조

`alert_rules.yml`을 확장할 때 참고할 수 있는 알림 예시는 다음과 같습니다:

- **DiffDurationHigh** – `diff_duration_ms_p95`가 200ms를 초과할 때 경고
- **DiffFailureRateHigh** – `diff_failures_total / diff_requests_total` 5분 비율이 5% 초과 시 경고
- **DiffThroughputLow** – `diff_requests_total` 5분 속도가 분당 0.6 미만일 때 경고
- **NodeCacheMemoryHigh** – `nodecache_resident_bytes`(scope="total")가 5GB 초과 시 경고
- **QueueCreateErrors** – `queue_create_error_total` 증가 시 경고
- **SentinelGap** – `sentinel_gap_count`로 센티널 누락 감지
- **OrphanQueuesGrowing** – 3시간 윈도에서 `orphan_queue_total` 증가 감지
- **QueueLagHigh** – `queue_lag_seconds`가 `queue_lag_threshold_seconds`를 초과할 때 경고
- **GatewayLatencyHigh** – `gateway_e2e_latency_p95`가 150ms 초과 시 경고
- **LostRequests** – `lost_requests_total` 기반 유실된 diff 제출 보고
- **GCSchedulerStall** – `gc_last_run_timestamp` 지연이 10분 초과 시 경고
- **NodeSlowProcessing** – `node_process_duration_ms` p95가 500ms 초과 시 경고
- **NodeFailures** – `node_process_failure_total` 증가 시 경고
- **CrossContextCacheHit** – `cross_context_cache_hit_total` > 0이면 치명(CRIT). 프로모션 재개 전 아래 런북을 따르세요.

## Grafana 대시보드

예시 Grafana 대시보드는 `dashboards/`에 있습니다. JSON 파일을 Grafana로 가져오면 큐 개수와 가비지 컬렉터 활동을 시각화할 수 있습니다. 대시보드는 DAG Manager가 노출하는 `orphan_queue_total` 지표를 사용합니다.

## Jsonnet 패키징 자동화

`operations/monitoring/seamless_v2.jsonnet`의 `seamless_v2_observability` Jsonnet 번들은 Helm 및 Terraform 아티팩트로 자동 패키징할 수 있습니다. 번들이 변경될 때마다 생성기를 실행하세요:

```bash
python scripts/package_monitoring_bundle.py
```

이 명령은 결과를 `operations/monitoring/dist/`에 기록하고, 재사용 가능한 샘플 오버라이드를 `operations/monitoring/samples/`로 내보냅니다:

- `dist/helm/seamless_v2_observability/`: 대시보드/레코딩 규칙이 포함된 `values.yaml`과 CI 친화적 `values-sample.yaml` 오버라이드가 포함된 완전 렌더링된 Helm 차트
- `dist/terraform/seamless_v2_observability/`: Kubernetes 프로바이더를 통해 대시보드/레코딩 규칙을 노출하는 Terraform 모듈과 자동화를 위한 `terraform.tfvars.example`
- `samples/`: 재생성 없이 바로 사용하는 스니펫(`*.helm-values.yaml`, `*.terraform.tfvars`)

Helm 차트는 `grafanaDashboards.extraDashboards`를 제공하여 `values.yaml`의 기본값을 덮어쓰지 않고 대시보드를 추가할 수 있습니다. 기본 목록을 완전히 대체하려는 경우에만 `grafanaDashboards.dashboards`를 설정하세요.

### Helm으로 배포

1. Grafana 배포가 `grafana_dashboard: "1"` 라벨이 있는 ConfigMap을 감시하도록 구성되어 있는지 확인합니다.
2. 사용자 값으로 차트를 설치합니다(샘플 파일은 프로덕션 네임스페이스에 맞춘 기본값 포함):

   ```bash
   helm upgrade --install seamless-observability \
     operations/monitoring/dist/helm/seamless_v2_observability \
     -f operations/monitoring/dist/helm/seamless_v2_observability/values-sample.yaml
   ```
3. Prometheus Operator 사용자는 `values-sample.yaml`의 네임스페이스가 배포와 일치하는지 확인하고, 필요하면 `prometheusRule.namespace`를 조정하세요.
4. 사용자 대시보드를 추가할 때는 오버라이드 파일의 `grafanaDashboards.extraDashboards`를 채워 Helm이 기본값과 병합하도록 합니다.

### Terraform으로 배포

1. 워크스페이스에 모듈을 추가합니다:

   ```hcl
   module "seamless_monitoring" {
     source = "../../operations/monitoring/dist/terraform/seamless_v2_observability"
   }
   ```
2. `terraform.tfvars.example`을 복사하고 네임스페이스, 라벨, 기능 토글을 조정합니다:

   ```bash
   cp operations/monitoring/dist/terraform/seamless_v2_observability/terraform.tfvars.example terraform.tfvars
   ```
3. Kubernetes 프로바이더 구성이 완료되면 플랜을 적용합니다:

   ```bash
   terraform init
   terraform apply
   ```

두 배포 방식 모두 Grafana용 동일한 ConfigMap과, Jsonnet 번들에 정의된 레코딩 규칙을 구체화하는 선택적 PrometheusRule을 생성합니다.

## QuestDB Recorder Demo

The script `qmtl/examples/questdb_parallel_example.py` runs two moving-average strategies in parallel while persisting every `StreamInput` payload to QuestDB. It starts the metrics server on port `8000` and prints aggregated Prometheus metrics when finished. Execute it as follows:

```bash
python -m qmtl.examples.questdb_parallel_example
```

Monitor `http://localhost:8000/metrics` during execution or check the printed output. Key counters include `node_processed_total` for processed events, `node_process_failure_total` for compute errors and `event_recorder_errors_total` when the recorder fails to persist rows.

## Gateway & DAG Manager 지표

두 서비스 모두 Prometheus 엔드포인트를 노출합니다. DAG Manager 메트릭 서버는 `qmtl service dagmanager metrics`로 시작하세요(기본 포트 8000은 `--port`로 변경 가능).
서킷 브레이커 활동은 다음 게이지로 추적합니다:

- `dagclient_breaker_open_total` — Gateway gRPC 클라이언트가 오픈될 때마다 증가
- `kafka_breaker_open_total` — DAG Manager의 Kafka admin 브레이커가 오픈될 때마다 증가

두 브레이커 모두 연속 3회 실패 후 오픈되며, 설정으로 변경할 수 없습니다. DAG Manager의 Neo4j 브레이커도 임계값 3을 사용합니다.

토픽별 Kafka 컨슈머 지연은 `queue_lag_seconds{topic}`로 노출되며, 구성된 임계값은 `queue_lag_threshold_seconds{topic}`로 표현됩니다.

DAG diff 처리와 관련된 표준 카운터는 다음과 같으며 SLA 기반 알림에 사용됩니다:

- `diff_requests_total` — 처리된 diff 요청 총량(처리량 기준선)
- `diff_failures_total` — 실패한 diff 요청 총량(실패율 계산용)
- `cross_context_cache_hit_total` — 반드시 0 유지. 증가 시 해당 컴포넌트를 리셋할 때까지 프로모션이 차단됩니다. 라벨에는 `node_id`, `world_id`, `execution_domain`, `as_of`, `partition`가 포함되며, 비어있거나 알 수 없는 값은 `__unset__`로 정규화됩니다.

### 런북: 교차 컨텍스트 캐시 히트(SLO = 0)

1. 경보 확인: `cross_context_cache_hit_total`이 0보다 큰지 확인하고, 디버깅을 위해 라벨 세트를 기록합니다.
2. 프로모션 중지: 영향을 받는 DAG 버전에 대한 릴리스를 중단합니다. 카운터가 0이 아닌 동안은 도구가 자동으로 차단해야 합니다.
3. 원인 추적: `(node_id, world_id, execution_domain, as_of, partition)` 라벨을 최근 배포와 비교합니다. 다음을 확인하세요:
   - 라이브 캐시 엔트리를 재사용한 백테스트/드라이런
   - `as_of` 누락(`__unset__` 라벨)으로 인한 compute-key 폴백
   - 파티셔닝 변경(테넌트 이동 등) 후 캐시 무효화 없음
4. 오염된 캐시 정리: 문제 노드의 SDK 캐시를 플러시하거나 올바른 컨텍스트로 DAG Manager 재계산을 트리거합니다. ComputeKey 격리가 재수립되었는지 확인합니다.
5. 카운터 리셋: 조치 후 컴포넌트를 재시작하거나 캐시 리셋 도구를 호출해 메트릭을 초기화합니다. 프로모션을 재개하기 전에 최소 10분간 0이 유지되는지 확인합니다.

권장 Prometheus 규칙은 지연(`diff_duration_ms_p95`), 실패율(`rate(diff_failures_total)/rate(diff_requests_total)`), 처리량(`rate(diff_requests_total)`)의 3가지 핵심 경보 그룹을 조합합니다. 예시는 `alert_rules.yml`을 참고하세요.

시간 기반 브레이커와 달리 QMTL은 트립된 브레이커를 닫기 위해 명시적 성공 신호가 필요합니다. 원격 상태를 확인하는 호출은 반환값을 검사한 뒤 상황에 맞게 `reset()`을 호출하세요:

```python
if await client.status():
    client.breaker.reset()
```

## SDK 지표

SDK 캐시 레이어는 소수의 Prometheus 지표를 제공합니다. 어떤 서비스든 `metrics.start_metrics_server()`를 호출해 노출할 수 있습니다.

### 지표 참조

| 이름 | 타입 | 설명 | 라벨 |
| ---- | ---- | ----------- | ------ |
| `cache_read_total` | Counter | Total number of cache reads grouped by upstream and interval | `upstream_id`, `interval` |
| `cache_last_read_timestamp` | Gauge | Unix timestamp of the most recent cache read | `upstream_id`, `interval` |
| `backfill_last_timestamp` | Gauge | Latest timestamp successfully backfilled | `node_id`, `interval` |
| `backfill_jobs_in_progress` | Gauge | Number of active backfill jobs | *(none)* |
| `backfill_failure_total` | Counter | Total number of backfill jobs that ultimately failed | `node_id`, `interval` |
| `backfill_retry_total` | Counter | Total number of backfill retry attempts | `node_id`, `interval` |
| `node_processed_total` | Counter | Total number of node compute executions | `node_id` |
| `node_process_duration_ms` | Histogram | Duration of node compute execution in milliseconds | `node_id` |
| `node_process_failure_total` | Counter | Total number of node compute failures | `node_id` |
| `cross_context_cache_hit_total` | Counter | Number of cache hits where context (world/domain/as_of/partition) mismatched | `node_id`, `world_id`, `execution_domain`, `as_of`, `partition` (missing values emitted as `__unset__`) |

애플리케이션에서 서버를 시작합니다:

```python
from qmtl.runtime.sdk import metrics

metrics.start_metrics_server(port=8000)
```

이후 `http://localhost:8000/metrics`에서 메트릭을 확인할 수 있습니다.

## 트레이싱(Tracing)

QMTL은 Gateway, DAG Manager, SDK에 대해 OpenTelemetry 스팬을 내보냅니다. Jaeger/Tempo 등 OTLP 호환 백엔드로 내보낼 수 있습니다.

### 구성(Configuration)

모든 프로세스가 동일 설정을 공유하도록 ``qmtl.yml``의 ``telemetry`` 섹션에 익스포터 엔드포인트를 정의합니다:

```yaml
telemetry:
  otel_exporter_endpoint: http://localhost:4318/v1/traces
```

로컬 개발 중 표준출력으로 스팬을 보려면 값을 ``console``로 설정하세요.

### Jaeger 쿼리 예시

전략 실행 후 Jaeger에서 서비스 이름으로 필터링하여 트레이스를 확인할 수 있습니다:

```txt
service="gateway"
```

트레이스를 선택하면 SDK의 HTTP 요청, Gateway 제출, DAG Manager로의 gRPC 호출 관계를 확인할 수 있습니다.


{{ nav_links() }}
