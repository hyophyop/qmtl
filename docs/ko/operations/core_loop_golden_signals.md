---
title: "Core Loop 골든 시그널 대시보드"
tags: [operations, monitoring, core-loop]
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# Core Loop 골든 시그널

T5 P1‑M2 골든 시그널 마일스톤을 운영 자산으로 고정한 문서다. [architecture/architecture.md](../architecture/architecture.md)와 [architecture/seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md)가 약속한 데이터/결정 경로를 Prometheus 지표와 Grafana 대시보드로 묶어, Core Loop 계약 테스트(`tests/e2e/core_loop`)와 동일한 시각을 제공한다.

## 골든 시그널 세트(데이터 → 결정/활성)

| 구간 | 핵심 메트릭 및 권장 SLO | 대시보드/경보 | 실패 시 해석 |
| --- | --- | --- | --- |
| 제출·결정성 | `gateway_e2e_latency_p95 < 150ms`, `diff_duration_ms_p95 < 200ms`, `cross_context_cache_hit_total = 0`, `nodeid_*_mismatch_total = 0` | `operations/monitoring.md`의 Gateway/DAG 패널, `alert_rules.yml` 기본 알림 | 지연 상승은 submit → diff 경로 병목, mismatch는 Determinism 체크리스트 위반. DAG 재계산 및 `operations/determinism.md` 런북 실행. |
| 백테스트 커버리지·데이터 SLA | `coverage_ratio >= 0.98`, `backfill_completion_ratio >= 0.9`, `histogram_quantile(0.99, seamless_sla_deadline_seconds{phase="total"}) < 240s`, `increase(seamless_conformance_flag_total[15m]) < 50` | `Seamless SLA Overview`/`Backfill Coordinator`/`Conformance Quality` (Jsonnet 번들), `SeamlessSla99thDegraded`·`SeamlessBackfillStuckLease`·`SeamlessConformanceFlagSpike` 경보 | 커버리지/갭·SLA 위반은 데이터 플레인 문제. world preset·Seamless 설정을 확인하고 Core Loop 계약 테스트의 warm-up/backtest 단계 실패와 연결한다. |
| WS 평가·적용 | `world_decide_latency_ms_p95 < 300ms`, `world_apply_duration_ms_p95 < 400ms`, `promotion_fail_total`/`demotion_fail_total` 무증가, `registry_write_fail_total = 0` | WorldService 지표 패널(커스텀/PromQL), Gateway 프록시 지표(`gateway_e2e_latency_p95`) | 결정/적용 지연은 정책 평가 병목 또는 Apply 재시도. `operations/activation.md` 플로우와 정책 평가 입력을 점검한다. |
| 활성화 전파(WS → Gateway/SDK) | `activation_skew_seconds p95 < 2s`, `event_relay_dropped_total`/`ws_dropped_subscribers_total = 0`(부하 테스트 외), ControlBus `ActivationUpdated` lag 안정 | `operations/ws_load_testing.md` 벤치 지표 패널, Gateway WS 팬아웃 패널 | 스큐/드롭은 WS 팬아웃 병목 또는 구독자 오류. ControlBus 큐·JWT 스코프·WS rate limit을 확인한다. |
| Core Loop 계약 게이트 | `tests/e2e/core_loop` CI 잡 통과, `alert_rules.yml` determinism/Seamless 경보 0 | CI 대시보드/빌드 로그 | 계약 테스트가 실패하면 위 골든 시그널 중 어떤 SLO가 깨졌는지 대시보드에서 먼저 확인 후 리런. |

## 대시보드 구성 가이드

- **Core Loop Overview(신규 패널 그룹)**: Gateway submit/latency, determinism counters, WS 결정/적용 지연, activation skew를 한 화면에 배치한다. 패널 소스는 `alert_rules.yml`에 이미 포함된 메트릭을 사용하며, Jsonnet/Helm 오버라이드로 추가한다.
- **데이터 플레인/백테스트 뷰**: 기존 `seamless_v2.jsonnet` 번들의 `Seamless SLA Overview`에 `coverage_ratio`와 `domain_gate_holds` 테이블을 추가하거나 상단에 preset/world 필터를 노출해 Core Loop 데모 월드 기준으로 정렬한다.
- **WS/팬아웃 뷰**: `operations/ws_load_testing.md`의 벤치마크 패턴을 그대로 Grafana 패널로 옮겨 `event_relay_*`, `ws_subscribers`, `activation_skew_seconds` 히스토그램을 나란히 배치한다.
- **테스트/게이트 뷰**: `tests/e2e/core_loop` CI 결과를 iframe/annotations로 포함하거나 빌드 ID를 패널 변수로 두어 실패 시 해당 시점의 골든 시그널 패널과 상관관계를 빠르게 파악한다.

Jsonnet 번들(`operations/monitoring/seamless_v2.jsonnet`)을 렌더링할 때 위 패널 그룹을 추가하면 Core Loop 골든 시그널 대시보드가 완성된다. 별도 JSON을 만들기 전이라도 Grafana에서 임시 패널을 만들어 SLO 트래킹을 시작할 수 있다.

## 계약 테스트 실패 시 해석 순서

1. **경보 확인**: `CrossContextCacheHit`·`Seamless*`·제출 지연 경보 중 무엇이 먼저 터졌는지 확인한다.
2. **데이터 vs 결정 경로 분리**
   - 데이터 경보/커버리지 저하 → Seamless 패널에서 `coverage_ratio`·`backfill_completion_ratio`와 conformance 플래그를 확인하고 world preset/SLAPolicy를 수정한다.
   - WS/팬아웃 지연/드롭 → `world_decide_latency_ms`·`activation_skew_seconds`·`event_relay_dropped_total`을 확인하고 WS 스케일링·팬아웃 큐를 조정한다.
3. **Determinism 재검증**: NodeID CRC/TagQuery mismatch가 있으면 DAG 재계산 후 Core Loop 계약 테스트를 재시도한다.
4. **CI 재실행**: 원인 조치 후 `tests/e2e/core_loop`를 로컬/CI에서 재실행해 골든 시그널과 계약 게이트가 함께 회복됐는지 확인한다.

## 관련 문서

- 아키텍처: [architecture.md §Core Loop 합의 요약](../architecture/architecture.md#core-loop-summary), [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md)
- 로드맵: Core Loop 합의 사항은 아키텍처 문서에 편입되었으며 별도 로드맵 문서는 아카이브됨.
- 운영: [monitoring.md](monitoring.md), [seamless_sla_dashboards.md](seamless_sla_dashboards.md), [ws_load_testing.md](ws_load_testing.md), [determinism.md](determinism.md)
