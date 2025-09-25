# Seamless Migration to Data Provider v2

The Seamless Data Provider v2 rollout introduces mandatory conformance checks,
SLA enforcement, and upgraded governance. This guide helps strategy and
platform teams migrate from the provisional v1 behaviour to the production v2
stack without disrupting live traffic.

## Prerequisites

- Upgrade to a build that includes `qmtl.runtime.sdk.seamless_data_provider`
  version 2.0.0 or later.
- Ensure the cluster has access to the distributed Backfill Coordinator service
  (deployed via `helm/seamless-backfill-coordinator`).
- Install the new observability bundle by applying
  `operations/monitoring/seamless_v2.jsonnet` or importing the packaged Grafana
  dashboard.

## Migration Stages

### 1. Enable Conformance Pipeline in Shadow Mode

1. Set `seamless.conformance.mode=shadow` in the environment configuration.
2. Monitor the `seamless_conformance_flag_total` metric. Zero flags means the
   dataset already complies.
3. Review generated regression reports in the `qmtl://observability/seamless`
   bucket and fix any detected schema drift or coverage gaps.

### 2. Adopt the Distributed Backfill Coordinator

1. Disable the legacy `InMemoryBackfillCoordinator` by removing it from the
   Seamless provider wiring.
2. Point `seamless.backfill.endpoint` at the Raft cluster service address.
3. Verify leases via the `Seamless SLA` Grafana dashboard. Any missing shards
   will surface through the `backfill_completion_ratio` metric.

### 3. Enforce SLAPolicy Deadlines

1. Promote policies from `dry-run` to `enforced` in `configs/seamless/sla`.
2. Confirm alert routing in PagerDuty/Slack with a staged violation using the
   `scripts/inject_sla_violation.py` helper.
3. Ensure each owning team has an escalation entry in the SLA runbook.

### 4. Switch Schema Validation to Strict

1. Update `schema_registry.validation_mode=strict` once canary metrics remain
   clean for at least 48 hours.
2. Document the promotion in `docs/operations/schema_registry_governance.md`
   and link the audit entry to the change request ticket.
3. Enable the `Schema Drift` alert so any regression triggers an on-call page.

### 5. Expand Test Coverage

- Enable the Seamless validation suite by running
  `uv run -m pytest tests/seamless -k "not slow"` in CI.
- Add property-based tests with Hypothesis for critical node paths.
- Wire failure-injection tests via the `seamless_fault_injection` fixture to
  confirm retries and SLA budget handling.

## Rollback Plan

If issues appear after enabling strict mode or SLA enforcement:

1. Toggle `seamless.conformance.mode=shadow` to stop blocking reads.
2. Set the SLA policy back to `dry-run`; this disables alerting but keeps
   metrics active for diagnosis.
3. Fallback to cached data by prioritising the storage source while the
   coordinator recovers.

Always record the incident and remediation actions in the Seamless postmortem
tracker so lessons flow back into the runbooks.

## Definition of Done

A migration is complete when:

- Conformance pipeline runs in blocking mode with no open regressions.
- Backfill coordinator leases and SLA dashboards show healthy baselines.
- Schema validation is strict and documented.
- Tests cover regressions, failure injection, and observability guards.
- The strategy runbooks no longer mention the provisional v1 behaviour.
