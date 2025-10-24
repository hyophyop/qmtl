---
title: "Seamless SLA 대시보드"
tags: [operations]
author: "QMTL Team"
last_modified: 2025-09-25
---

{{ nav_links() }}

# Seamless SLA 대시보드

> **상태:** 이 런북이 참조하는 대시보드와 경보 규칙은 실시간 메트릭과 연결되어 있습니다. Jsonnet 번들을 배포하고 프로덕션 환경에 경보를 연동하세요. 분산 코디네이터와 SLA 엔진은 QMTL v2에 포함되어 있습니다.

이 런북은 Seamless Data Provider v2와 함께 제공되는 관측 패키지를 설명합니다. 아래 변경 사항은 이슈 #1148 이전의 임시 가이드를 대체합니다.

## 대시보드 번들

Grafana에 `operations/monitoring/seamless_v2.jsonnet`(또는 렌더링된 JSON)을 가져오면 다음 세 가지 핵심 대시보드가 프로비저닝됩니다.

1. **Seamless SLA Overview** – `seamless_sla_deadline_seconds` 히스토그램, 도메인별 지연 퍼센타일, 에러 버짓 게이지를 표시합니다.
2. **Backfill Coordinator Health** – 리스 수, 스테일 클레임 감지, `backfill_completion_ratio` 추이를 시각화합니다.
3. **Conformance Quality** – 플래그 합계, 스키마 경고, 리그레션 리포트 검사 결과를 강조합니다.

Prometheus가 Seamless 런타임을 스크레이프하면 대시보드가 올바르게 렌더링됩니다. 번들은 아래에 설명된 코디네이터 및 SLA 메트릭에 의존합니다.

## 메트릭 및 경보

런타임은 다음 메트릭을 노출합니다.

- `seamless_sla_deadline_seconds` (히스토그램) – `storage_wait`, `backfill_wait`, `live_wait`, `total` 단계별 `phase` 라벨을 포함합니다. 99퍼센타일이 예산에 근접하면 경보를 발송하세요.
- `backfill_completion_ratio` – 분산 코디네이터가 관찰한 리스별 완료 비율을 보고하는 게이지입니다.
- `seamless_conformance_flag_total` – `ConformancePipeline` 이 정규화 경고를 기록할 때 증가하는 카운터입니다. 개별 플래그 유형은 대시보드의 "Flag Breakdown" 테이블에 표시되고, 집계 경고는 `seamless_conformance_warning_total` 을 증가시킵니다.
- 단계별 지연 히스토그램: `seamless_storage_wait_ms`, `seamless_backfill_wait_ms`, `seamless_live_wait_ms`, `seamless_total_ms`. 모두 `{node_id, interval, world_id}` 라벨을 포함해 도메인별 필터링이 가능합니다.
- 커버리지/신선도 게이지: `coverage_ratio`, `live_staleness_seconds` 는 제공 범위 대비 요청 범위와 최신 바에 대한 갭을 노출합니다. 동일 라벨 세트를 공유하며 도메인 게이트 HOLD 자동화를 보조합니다.
- 갭 복구 및 코디네이터 헬스: `gap_repair_latency_ms` 는 누락 구간 복구에 걸린 시간을 추적합니다. `backfill_completion_ratio` 는 여전히 핵심 지표이며, `seamless_rl_tokens_available`, `seamless_rl_dropped_total` 로 Redis 토큰 버킷 여유를 감시합니다.
- 아티팩트 관측: `artifact_publish_latency_ms`, `artifact_bytes_written`, `fingerprint_collisions` 는 게시 지연, 저장소 처리량, 중복 지문을 빠르게 파악할 수 있게 합니다.
- 도메인 다운그레이드 카운터: `domain_gate_holds`, `partial_fill_returns` 는 SLA 정책이 응답을 다운그레이드할 때마다 이유 라벨과 함께 증가합니다. HOLD/PARTIAL_FILL 급증과 경보 폭주를 상관 분석하는 데 활용하세요.

`alert_rules.yml` 에 `seamless-*` prefix 경보 규칙이 추가되었습니다.

- `SeamlessSla99thDegraded` – `seamless_sla_deadline_seconds` 99퍼센타일이 5분 연속 예산을 초과하면 경보.
- `SeamlessBackfillStuckLease` – `backfill_completion_ratio` 가 특정 리스에서 50% 미만으로 유지되면 페이지.
- `SeamlessConformanceFlagSpike` – 15분 동안 정규화 플래그가 급증하면 알림.

해당 경보가 페이지해야 하는 환경에는 PagerDuty와 Slack 라우트를 구성하세요. 경보 주석은 이 런북으로 연결됩니다.

## 검증 도구

세 가지 운영 스크립트가 대시보드와 함께 제공됩니다.

- `scripts/inject_sla_violation.py` 는 합성 SLA 메트릭을 생성합니다. Prometheus 노출 텍스트를 파일로 저장하거나 임시 HTTP 서버로 제공할 수 있어, 실제 사고 없이 Grafana 패널과 경보를 검증할 수 있습니다.

  ```bash
  uv run scripts/inject_sla_violation.py seam-node-1 --duration 240 --repetitions 5 --write-to /tmp/seamless.metrics
  ```

- `scripts/lease_recover.py` 는 코디네이터 리스를 강제로 실패/완료 처리해 걸림 상태를 해소합니다. 코디네이터 점검 엔드포인트가 반환하는 `KEY:TOKEN` 페어를 제공하세요.

  ```bash
  uv run scripts/lease_recover.py --coordinator-url https://coordinator/v1 lease-A:deadbeef lease-B:feedface
  ```

- `scripts/seamless_health_check.py` 는 환경 변수, 분산 코디네이터, Prometheus 메트릭을 검사해 프로덕션 배포를 검증합니다. CLI는 [`httpx`](https://www.python-httpx.org/) 에 의존하며 기본적으로 `QMTL_SEAMLESS_COORDINATOR_URL`, `QMTL_PROMETHEUS_URL` 환경 변수를 읽습니다.

  ```bash
  uv run python scripts/seamless_health_check.py \
    --prometheus-metric backfill_completion_ratio \
    --prometheus-metric seamless_sla_deadline_seconds
  ```

`--prometheus-url`, `--coordinator-url` 플래그로 엔드포인트를 재정의하거나 실행 전에 환경 변수를 설정할 수 있습니다. 비프로덕션 환경에서는 헬스 체크의 `--timeout` 플래그와 다른 스크립트의 `--dry-run` 모드를 조합하세요.

## 트레이싱과 로깅

- **트레이싱:** `seamless.pipeline` 스팬은 예산이 적용될 때 `sla.phase` 속성을 포함합니다. 향후 릴리스에서 스키마 메타데이터를 확장할 예정입니다.
- **로깅:** 코디네이터와 SLA 레이어는 각각 `seamless.backfill`, `seamless.sla` 로 로깅합니다. 구조화된 로그를 활용해 경보를 리스 ID 또는 문제 노드와 연결하세요. 도메인 게이트 다운그레이드 이벤트는 `seamless.domain_gate.downgrade` 로그를 남기며, `dataset_fingerprint`, `as_of` 필드로 어떤 스냅샷이 HOLD 응답에 사용됐는지 감사 추적이 가능합니다.

## 런북 절차

경보가 발생하면:

1. Seamless SLA Overview 대시보드를 열어 영향을 받은 도메인을 확인합니다.
2. Backfill Coordinator Health 대시보드로 리스가 멈췄는지 확인하고 필요하면 `scripts/lease_recover.py` 로 회수합니다.
3. `seamless.pipeline` 스팬에서 이상 트레이스를 확인합니다.
4. `operations/monitoring.md` 의 담당 매트릭스를 따라 에스컬레이션하고 Seamless 포스트모템 트래커에 사고를 기록합니다.

{{ nav_links() }}
