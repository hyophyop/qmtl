# World Validation 운영 가시성 (SLO/대시보드/알람)

이 문서는 WorldService 기반 World Validation 계층을 운영 스케일에서 신뢰할 수 있도록, 핵심 SLI/SLO와 대시보드·알람 기준을 정리합니다.

## 범위

- Risk Signal Hub 스냅샷 수집(HTTP push + ControlBus 소비)
- Extended validation 워커(cohort/portfolio/stress/live) 실행
- Live monitoring run(materialize stage=live EvaluationRun)
- EvaluationRun 기반의 `validation_health` / SR 11-7 인바리언트 점검

## SLI/SLO 초안

### 1) RiskHub Freshness

- SLI: `risk_hub_snapshot_lag_seconds{world_id}`
- 권장 SLO:
  - WARNING: `> 600s` (10m)
  - CRITICAL: `> 1800s` (30m)

### 2) Snapshot Processing Health (ControlBus Consumer)

- SLI:
  - 처리량: `rate(risk_hub_snapshot_processed_total[5m])`
  - 실패율: `rate(risk_hub_snapshot_failed_total[5m]) / (rate(risk_hub_snapshot_processed_total[5m]) + rate(risk_hub_snapshot_failed_total[5m]))`
  - DLQ: `increase(risk_hub_snapshot_dlq_total[5m])`
  - Dedupe/TTL: `increase(risk_hub_snapshot_dedupe_total[5m])`, `increase(risk_hub_snapshot_expired_total[5m])`

### 3) Extended Validation Worker

- SLI:
  - 성공/실패: `rate(extended_validation_run_total{status="success"}[5m])`, `rate(extended_validation_run_total{status=~"failure|enqueue_failed"}[5m])`
  - p95 latency: `histogram_quantile(0.95, sum(rate(extended_validation_run_latency_seconds_bucket[5m])) by (le, world_id, stage))`

### 4) Live Monitoring Materialization

- SLI:
  - 실행 성공/실패: `rate(live_monitoring_run_total{status="success"}[5m])`, `rate(live_monitoring_run_total{status="failure"}[5m])`
  - 업데이트된 전략 수: `increase(live_monitoring_run_updated_strategies_total[1h])`
- 운영 엔트리포인트(예시):
  - Live run 생성(크론/데몬): `uv run python scripts/live_monitoring_worker.py --interval-seconds 3600`
  - 리포트 생성(Markdown/JSON): `uv run python scripts/generate_live_monitoring_report.py --world <world_id> --output live_report.md`
  - GitHub Actions 스케줄(권장): `.github/workflows/live-monitoring-schedule.yml` (secrets 미설정 시 자동 skip + 리포트 아티팩트 업로드)

### 5) Validation Health / Invariants

- EvaluationRun의 `metrics.diagnostics.validation_health.metric_coverage_ratio`는 Prometheus가 아니라 **EvaluationRun 저장 레이어**에 기록됩니다.
- 운영에서의 체크 방법(권장):
  - 인바리언트 리포트: `GET /worlds/{world_id}/validations/invariants`
  - 최신 EvaluationRun 조회 후 `diagnostics.validation_health`를 샘플링(월드/스테이지별)

## Alertmanager 룰(예시 스니펫)

{% raw %}
```yaml
groups:
  - name: world_validation
    rules:
      - alert: RiskHubSnapshotLagHigh
        expr: risk_hub_snapshot_lag_seconds > 1800
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "RiskHub snapshot lag high"
          description: "world={{ $labels.world_id }} lag={{ $value }}s"

      - alert: RiskHubSnapshotDlqSpike
        expr: increase(risk_hub_snapshot_dlq_total[10m]) > 0
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "RiskHub DLQ spike"
          description: "world={{ $labels.world_id }} stage={{ $labels.stage }}"

      - alert: ExtendedValidationFailures
        expr: increase(extended_validation_run_total{status=~\"failure|enqueue_failed\"}[10m]) > 0
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "Extended validation failures"
          description: "world={{ $labels.world_id }} stage={{ $labels.stage }}"

      - alert: LiveMonitoringNoRuns
        expr: (sum(increase(live_monitoring_run_total[6h])) or vector(0)) < 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Live monitoring job not running"
          description: "No live monitoring runs observed for 6 hours"

      - alert: LiveMonitoringFailures
        expr: sum(increase(live_monitoring_run_total{status=\"failure\"}[10m])) > 0
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "Live monitoring failures detected"
          description: "Live monitoring worker failures observed"
```
{% endraw %}

## 대시보드(권장 패널)

- RiskHub freshness: `risk_hub_snapshot_lag_seconds` (world_id 별)
- Snapshot pipeline health: processed/failed/retry/dlq/dedupe/expired
- Extended validation: success/failure, p95 latency
- Live monitoring: run success/failure, updated strategies
- Invariants/Health: `/validations/invariants` 결과(운영 스크립트/외부 폴러로 주기 수집 권장)

### 대시보드 스펙(Repo 내 텍스트)

- Grafana 패널 스펙(텍스트): `operations/monitoring/world_validation_v1.jsonnet`

### 운영 증빙(권장)

- 증빙 템플릿: `operations/monitoring/samples/world_validation_observability_evidence.md`
