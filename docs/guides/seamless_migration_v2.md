# Seamless Migration to Data Provider v2

> **Status:** Migration guidance is now actionable. The distributed backfill
> coordinator, SLA engine, and supporting metrics ship with the default runtime.
> Use this checklist to move strategies onto the v2 stack and retire v1
> fallbacks.

The Seamless Data Provider v2 rollout introduces mandatory SLA enforcement,
distributed backfill coordination, and upgraded observability. Schema registry
governance remains optional, but teams should begin adopting it as the final v2
milestone.

## Prerequisites

- Ensure the `seamless-backfill-coordinator` service is deployed and reachable;
  set `seamless.coordinator_url` in runtime configuration.
- Roll out the observability bundle from `operations/monitoring/seamless_v2.jsonnet`
  so `backfill_completion_ratio` and `seamless_sla_deadline_seconds` surface in
  Grafana.
- Capture SLA targets in configuration. Policies are now enforced at runtime.

## Migration Stages

### 1. Prototype the Conformance Pipeline

1. Instantiate `ConformancePipeline` explicitly in integration tests to collect
   normalization reports. Runtime wiring will remain opt-in until the defaults
   switch to blocking mode.
2. Capture `seamless_conformance_flag_total` locally (or in staging) to gauge
   drift. Production scraping is not yet in place.
3. Update dashboards and alert queries to include the new `interval` and
   `world_id` labels emitted by `seamless_conformance_flag_total`/`_warning_total`.
4. Document schema assumptions so promotion to strict mode can happen quickly
   once the registry support lands.

### 2. Adopt the Distributed Backfill Coordinator

1. Configure strategies to rely on the default coordinator. When
   `seamless.coordinator_url` is set the SDK instantiates
   `DistributedBackfillCoordinator` automatically.
2. Validate `backfill_completion_ratio` in staging to ensure leases converge and
   shards are not duplicated.
3. Document recovery procedures (`scripts/lease_recover.py`) for on-call use and
   rehearse dry runs in staging before cutting production traffic.

### 3. Enforce SLAPolicy Budgets

1. Wire concrete deadlines into `SLAPolicy` instances for each Seamless consumer.
2. Verify that breaches raise `SeamlessSLAExceeded` in staging and that alerts
   fire via the `seamless-sla-*` rules. The helper script
   `scripts/inject_sla_violation.py` can inject synthetic histogram samples to
   validate the pipeline before production traffic hits the new thresholds.
3. Update runbooks with the new troubleshooting flow described in the SLA
   dashboards guide.

### 4. Plan Schema Validation Rollout

1. Use the `ConformancePipeline` reports to identify columns that fail
   normalization today.
2. Decide which datasets will adopt strict validation first once registry
   support is wired in.
3. Prepare alert definitions but leave them disabled until metrics are emitted.

### 5. Expand Test Coverage

- Keep the existing Seamless validation suite in CI so regressions surface early.
- Add property-based tests with Hypothesis for critical node paths to cover the
  distributed coordinator edge cases.
- Exercise the `seamless_fault_injection` fixture to validate retry semantics
  against SLA deadlines.

## Rollback Plan

If issues appear once the new components roll out:

1. Toggle `seamless.conformance.mode=shadow` to stop blocking reads while
   keeping visibility into normalization gaps.
2. Revert any SLA configuration overrides until the enforcement layer stabilises.
3. Fallback to cached data by prioritising the storage source while the new
   coordinator recovers.

Always record the incident and remediation actions in the Seamless postmortem
tracker so lessons flow back into the runbooks.

## Definition of Done

Mark migrations complete when the following criteria hold:

- Conformance pipeline runs in blocking mode with no open regressions.
- Backfill coordinator leases and SLA dashboards show healthy baselines.
- Schema validation is strict and documented (or an approved exception is
  recorded while registry work finishes).
- Tests cover regressions, failure injection, and observability guards.
- Strategy runbooks reference the distributed coordinator and SLA dashboards
  instead of the provisional v1 behaviour.
