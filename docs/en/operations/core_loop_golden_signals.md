---
title: "Core Loop Golden Signals"
tags: [operations, monitoring, core-loop]
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# Core Loop Golden Signals

This document lands the T5 P1‑M2 golden-signal milestone as an operational asset. It ties the data/decision path promised in [architecture/architecture.md](../architecture/architecture.md) and [architecture/seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md) to Prometheus metrics and Grafana dashboards so operators see the same surface protected by the Core Loop contract suite (`tests/e2e/core_loop`).

## Golden-signal set (data → decision/activation)

| Stage | Key metrics & suggested SLO | Dashboard/alert | How to read failures |
| --- | --- | --- | --- |
| Submit & determinism | `gateway_e2e_latency_p95 < 150ms`, `diff_duration_ms_p95 < 200ms`, `cross_context_cache_hit_total = 0`, `nodeid_*_mismatch_total = 0` | Gateway/DAG panels in `operations/monitoring.md`, default alerts in `alert_rules.yml` | Latency spikes point to submit → diff bottlenecks; mismatches violate the determinism checklist. Recompute DAG and follow `operations/determinism.md`. |
| Backtest coverage & data SLA | `coverage_ratio >= 0.98`, `backfill_completion_ratio >= 0.9`, `histogram_quantile(0.99, seamless_sla_deadline_seconds{phase="total"}) < 240s`, `increase(seamless_conformance_flag_total[15m]) < 50` | `Seamless SLA Overview` / `Backfill Coordinator` / `Conformance Quality` (Jsonnet bundle), `SeamlessSla99thDegraded` / `SeamlessBackfillStuckLease` / `SeamlessConformanceFlagSpike` alerts | Coverage/gap or SLA violations are data-plane issues. Check world presets/Seamless config and correlate with warm-up/backtest failures in the Core Loop contract suite. |
| WS evaluation & apply | `world_decide_latency_ms_p95 < 300ms`, `world_apply_duration_ms_p95 < 400ms`, no growth in `promotion_fail_total`/`demotion_fail_total`, `registry_write_fail_total = 0` | WorldService panels (custom/PromQL) plus Gateway proxy metrics (`gateway_e2e_latency_p95`) | Evaluation/apply latency indicates policy bottlenecks or apply retries. Inspect `operations/activation.md` flows and the policy inputs. |
| Activation propagation (WS → Gateway/SDK) | `activation_skew_seconds p95 < 2s`, `event_relay_dropped_total`/`ws_dropped_subscribers_total = 0` outside load tests, stable ControlBus `ActivationUpdated` lag | Panels based on `operations/ws_load_testing.md`, Gateway WS fan-out panels | Skew/drops imply WS fan-out stress or subscriber issues. Check ControlBus queues, JWT scope, and WS rate limits. |
| Core Loop contract gate | `tests/e2e/core_loop` CI job passes, no determinism/Seamless alerts from `alert_rules.yml` | CI dashboard/build logs | When the contract suite fails, first check which SLO above broke, then re-run after remediation. |

## Dashboard composition guide

- **Core Loop Overview (new group):** Place Gateway submit/latency, determinism counters, WS evaluation/apply latency, and activation skew on one page. These metrics already back the `alert_rules.yml` entries; add them via Jsonnet/Helm overrides.
- **Data-plane/backtest view:** Extend the `Seamless SLA Overview` dashboard in `seamless_v2.jsonnet` with `coverage_ratio` and `domain_gate_holds` tables or surface preset/world filters so panels align with the Core Loop demo world.
- **WS/fan-out view:** Mirror the benchmarks from `operations/ws_load_testing.md` in Grafana with `event_relay_*`, `ws_subscribers`, and `activation_skew_seconds` histograms side by side.
- **Test/gate view:** Embed `tests/e2e/core_loop` CI results (iframe/annotations) or expose the build ID as a panel variable so failed runs correlate with the golden-signal panels for the same window.

When rendering the Jsonnet bundle (`operations/monitoring/seamless_v2.jsonnet`), add the groups above to produce a Core Loop golden-signal dashboard. Even before baking JSON, stand up ad-hoc panels in Grafana to start tracking the SLOs.

## Interpreting contract test failures

1. **Check alerts:** note whether `CrossContextCacheHit`, `Seamless*`, or submit latency alerts fired first.
2. **Separate data vs. decision paths**
   - Data alerts/coverage drops → inspect `coverage_ratio`, `backfill_completion_ratio`, and conformance flags, then adjust world presets/SLAPolicy.
   - WS/fan-out latency/drops → inspect `world_decide_latency_ms`, `activation_skew_seconds`, and `event_relay_dropped_total`, then tune WS scaling and fan-out queues.
3. **Re-validate determinism:** if NodeID CRC/TagQuery mismatches occur, recompute the DAG and re-run the Core Loop suite.
4. **Re-run CI:** after fixes, rerun `tests/e2e/core_loop` locally/CI to confirm the golden signals and the contract gate recovered together.

## Related docs

- Architecture: [architecture.md §7 Determinism & Operational Checklist](../architecture/architecture.md), [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md)
- Roadmap: [Core Loop roadmap T5 P1‑M2](../design/core_loop_roadmap.md)
- Operations: [monitoring.md](monitoring.md), [seamless_sla_dashboards.md](seamless_sla_dashboards.md), [ws_load_testing.md](ws_load_testing.md), [determinism.md](determinism.md)
