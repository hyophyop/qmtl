# 운영 대시보드 인덱스 (Grafana)

본 문서는 QMTL 운영 관측(Observability)을 위한 Grafana 대시보드 모음과 구성 방법을 안내합니다. Prometheus 지표 노출과 스크래핑, Helm/Terraform 프로비저닝은 모니터링 가이드와 함께 사용하세요.

- 모니터링/알림 개요: docs/operations/monitoring.md
- Seamless SLA 대시보드: docs/operations/seamless_sla_dashboards.md
- 샘플 대시보드 JSON: qmtl/docs/operations/dashboards/

## 전제 조건

- Prometheus가 QMTL 컴포넌트의 지표 엔드포인트를 스크래핑 중일 것
  - DAG Manager: `qmtl service dagmanager metrics --port 8000`
  - Gateway: 코드에 내장된 `start_metrics_server(port=8000)` 사용
  - SDK/런타임: `from qmtl.runtime.sdk import metrics; metrics.start_metrics_server()`
- Grafana가 설치되어 있으며 ConfigMap 기반 대시보드 프로비저닝을 활성화했을 것 (`grafana_dashboard: "1"` 라벨)
- Helm/Terraform로 Jsonnet 번들 배포를 원하면 monitoring.md의 “Jsonnet packaging automation” 절차를 수행

## 데이터 소스와 핵심 메트릭

QMTL는 Gateway/DAG Manager/SDK에서 다음과 같은 메트릭을 노출합니다. 전체 목록과 의미는 문서에 상세화되어 있습니다.

- DAG Manager: `diff_duration_ms_p95`, `diff_requests_total`, `diff_failures_total`, `orphan_queue_total`, `gc_last_run_timestamp`, `queue_lag_seconds{topic=...}`, `nodecache_resident_bytes`, `kafka_breaker_open_total`, `dagmanager_active_version_weight{version=...}` 등
- Gateway: `gateway_e2e_latency_p95`, `lost_requests_total`, `worlds_proxy_latency_p95`, `worlds_cache_hit_ratio`, `dagclient_*`, `worlds_*_breaker_*`, `ws_*`, `event_relay_*`, `controlbus_lag_ms`, `gw_pretrade_*` 등
- SDK: `node_processed_total`, `node_process_duration_ms`, `node_process_failure_total`, `cache_read_total`, `cache_last_read_timestamp`, `cross_context_cache_hit_total` 등

자세한 참조: docs/operations/monitoring.md “Alert Rules”, “SDK Metrics” 섹션

## 제공/계획된 대시보드

아래 표는 포함된 대시보드와 향후 작업 항목을 요약합니다.

1) 포함됨: GC/그래프 상태
- 파일: qmtl/docs/operations/dashboards/gc_dashboard.json
- 패널 예시: `orphan_queue_total` 추이 그래프
- 제안 패널 추가: `gc_last_run_timestamp`, `compute_nodes_total`, `queues_total`, `queue_lag_seconds` vs `queue_lag_threshold_seconds` 비교, `kafka_breaker_open_total`

2) 계획: Gateway Overview
- 패널 아이디어:
  - 지연/처리량: `gateway_e2e_latency_p95`, `rate(lost_requests_total[5m])`
  - WorldService 프록시: `worlds_proxy_latency_p95`, `worlds_cache_hit_ratio`, `worlds_proxy_requests_total`
  - 브레이커 상태: `dagclient_breaker_state`, `dagclient_breaker_open_total`, `worlds_breaker_state`
  - ControlBus/WS: `controlbus_lag_ms{topic=~".*"}`, `ws_subscribers`, `rate(event_relay_events_total[5m])`, `rate(event_relay_dropped_total[5m])`, `ws_connections_total`, `ws_disconnects_total`, `ws_auth_failures_total`
  - Pre-trade: `gw_pretrade_rejection_ratio{world_id=...}`, `gw_pretrade_rejections_total by reason`

3) 계획: DAG Manager Overview
- 패널 아이디어:
  - Diff 품질: `diff_duration_ms_p95`, `rate(diff_requests_total[5m])`, `rate(diff_failures_total[5m])`, 실패율 = `rate(diff_failures_total[5m])/rate(diff_requests_total[5m])`
  - GC/그래프: `orphan_queue_total`, `gc_last_run_timestamp`, `compute_nodes_total`, `queues_total`
  - 큐 지연: `queue_lag_seconds` vs `queue_lag_threshold_seconds` (topic별 테이블/막대)
  - 캐시: `nodecache_resident_bytes{scope="total"}`
  - 버전 트래픽 분포: `dagmanager_active_version_weight{version=~".*"}`

4) 계획: SDK/노드 성능
- 패널 아이디어:
  - 노드 처리량/지연: `rate(node_processed_total[5m]) by (node_id)`, `histogram_quantile(0.95, sum(rate(node_process_duration_ms_bucket[5m])) by (le, node_id))`
  - 실패/품질: `rate(node_process_failure_total[5m]) by (node_id)`, `cross_context_cache_hit_total` 트렌드
  - 캐시 활동: `rate(cache_read_total[5m]) by (upstream_id, interval)`

5) 포함됨: Seamless SLA 번들
- 문서: docs/operations/seamless_sla_dashboards.md
- 구성: Jsonnet → Helm/Terraform로 프로비저닝 (monitoring.md 참조)

## Grafana 가져오기/프로비저닝

가져오기(수동)

1. Grafana → Dashboards → Import → “Upload JSON file”로 `gc_dashboard.json` 업로드
2. 데이터 소스로 Prometheus를 선택하고 저장

프로비저닝(권장)

- monitoring.md의 Helm/Terraform 절차를 사용해 ConfigMap으로 자동 배포
- Jsonnet 번들을 사용할 경우 `grafanaDashboards.extraDashboards` 에 신규 대시보드를 병합 추가

## 운영 체크리스트(권고 임계치)

- Diff 실패율 < 5% 유지, P95 `diff_duration_ms_p95` < 200ms
- Gateway P95 `gateway_e2e_latency_p95` < 150ms, `lost_requests_total` 증가 없음
- ControlBus `event_relay_dropped_total` 0 유지, `controlbus_lag_ms` 안정적
- 큐 지연 `queue_lag_seconds` ≤ `queue_lag_threshold_seconds`
- 캐시 상주 메모리 `nodecache_resident_bytes(scope="total")` < 5GB

## TODO (작업 항목)

- [ ] Gateway Overview 대시보드 JSON 초안 작성 및 저장소 반영
- [ ] DAG Manager Overview 대시보드 JSON 초안 작성 및 저장소 반영
- [ ] SDK/노드 성능 대시보드 JSON 초안 작성 및 저장소 반영
- [ ] Helm/Terraform 값 파일에 신규 대시보드 프로비저닝 추가(`grafanaDashboards.extraDashboards`)
- [ ] `alert_rules.yml` 에 관련 알림 룰 보강, 운영 임계치 반영
