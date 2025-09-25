# Seamless Migration to Data Provider v2

> **Status:** Migration guidance is provisional. The runtime continues to expose
> the v1 behaviour by default, and many of the v2 capabilities referenced below
> are still being implemented. Treat the checklist as preparation work for when
> issues #1148–#1152 land rather than an immediately actionable runbook.

The Seamless Data Provider v2 rollout will eventually introduce mandatory
conformance checks, SLA enforcement, and upgraded governance. Until the
underlying services ship, this document focuses on the steps teams can take to
stay aligned with the roadmap and avoid premature configuration changes.

## Prerequisites

- Track the release that introduces the distributed coordinator and SLA engine.
  The current package exports only the in-memory coordinator stub.
- Hold off on any Helm deployments for `seamless-backfill-coordinator`; the
  charts will be published alongside the implementation work.
- Skip the observability bundle for now. The referenced Jsonnet manifests do not
  exist yet and will be added when metrics become available.

## Migration Stages

### 1. Prototype the Conformance Pipeline

1. Instantiate `ConformancePipeline` explicitly in integration tests to collect
   normalization reports. Runtime wiring will remain opt-in until the defaults
   switch to blocking mode.
2. Capture `seamless_conformance_flag_total` locally (or in staging) to gauge
   drift. Production scraping is not yet in place.
3. Document schema assumptions so promotion to strict mode can happen quickly
   once the registry support lands.

### 2. Prepare for the Distributed Backfill Coordinator

1. Keep using `InMemoryBackfillCoordinator` until the Raft implementation is
   merged. Attempting to switch today will raise import errors.
2. Inventory which strategies will require coordinated leases so you can test
   with the new service once available.
3. Plan integration tests around the future `backfill_completion_ratio` metric
   even though it is not emitted yet.

### 3. Draft SLAPolicy Expectations

1. Capture target deadlines in documentation or configuration comments. The
   `SLAPolicy` dataclass currently records intent only.
2. Mock incident walkthroughs to validate escalation paths before alerts exist.
3. Contribute to the SLA runbook template so it is ready for the enforcement
   launch.

### 4. Plan Schema Validation Rollout

1. Use the `ConformancePipeline` reports to identify columns that fail
   normalization today.
2. Decide which datasets will adopt strict validation first once registry
   support is wired in.
3. Prepare alert definitions but leave them disabled until metrics are emitted.

### 5. Expand Test Coverage

- Keep the existing Seamless validation suite in CI so regressions surface even
  before v2 lands.
- Add property-based tests with Hypothesis for critical node paths to build
  confidence ahead of the rollout.
- Experiment with the `seamless_fault_injection` fixture locally; the retry
  semantics will evolve alongside the SLA implementation.

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

Do not mark migrations complete until the supporting features are live. When the
implementation is available, use the following criteria:

- Conformance pipeline runs in blocking mode with no open regressions.
- Backfill coordinator leases and SLA dashboards show healthy baselines.
- Schema validation is strict and documented.
- Tests cover regressions, failure injection, and observability guards.
- The strategy runbooks no longer mention the provisional v1 behaviour.
