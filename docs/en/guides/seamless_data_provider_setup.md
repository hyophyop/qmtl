# Seamless Data Provider Setup Guide

This guide describes step‑by‑step configuration for running the Seamless Data
Provider (SDP) in production, evaluates operational complexity, and offers
practical suggestions to improve usability.

## 1. Prerequisites

1. **Storage and fetch layers** — prepare a historical store (e.g., QuestDB)
   and a `DataFetcher` to populate it. `EnhancedQuestDBProvider` composes store
   and fetch layers with priority‑based routing for transparent reads.
2. **Distributed backfill coordinator** — set `seamless.coordinator_url` in
   `qmtl.yml` so the SDK can coordinate backfill among workers.
3. **Conformance Pipeline** — enabled by default; produces schema/time rollups
   and reports; blocks on violations unless `partial_ok=True`.
4. **SLA Policy** — configure `SLAPolicy` to track per‑stage wait times and emit
   exceptions/metrics on budget overruns.
5. **Artifacts/metrics** — expose observability metrics
   (`seamless_sla_deadline_seconds`, `backfill_completion_ratio`, etc.) in
   Prometheus and wire dashboards.

## 2. Step‑by‑step configuration

1. **Runtime settings**
   ```yaml
   seamless:
     coordinator_url: https://seamless-coordinator.internal
    publish_fingerprint: true      # (optional) publish artifact fingerprints
    preview_fingerprint: false     # (optional) allow preview fingerprints
    early_fingerprint: false       # (optional) allow early fingerprints
   ```
   YAML controls distributed backfill and artifact fingerprint publication to
   improve auditing and reproducibility.

2. **Create the provider**
   ```python
   from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
   from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy
   from myapp.fetchers import HistoricalFetcher, LiveFetcher

   provider = EnhancedQuestDBProvider(
       dsn="postgresql://questdb:8812/qmtl",
       table="market_data",
       fetcher=HistoricalFetcher(),
       live_fetcher=LiveFetcher(),
       strategy=DataAvailabilityStrategy.SEAMLESS,
       partial_ok=False,
   )
   ```
   The provider evaluates requests in order: cache → storage → backfill → live,
   and chooses between auto backfill and partial responses based on the
   configured strategy.

3. **Inject SLA and conformance policies (optional)**
   ```python
   from qmtl.runtime.sdk.sla import SLAPolicy
   from qmtl.runtime.sdk.conformance import ConformancePipeline

   provider = EnhancedQuestDBProvider(
       dsn="postgresql://questdb:8812/qmtl",
       fetcher=HistoricalFetcher(),
       strategy=DataAvailabilityStrategy.SEAMLESS,
       sla=SLAPolicy(total_deadline_ms=60000, storage_deadline_ms=5000),
       conformance=ConformancePipeline.partial_ok(True),
   )
   ```
   SLA configuration enforces service levels via metrics and exceptions;
   the conformance pipeline governs data quality.

4. **Connect to StreamInput**
   ```python
   from qmtl.runtime.nodes.stream_input import StreamInput

   stream = StreamInput(history_provider=provider)
   ```
   The provider is drop‑in compatible with existing nodes—no code changes
   required.

5. **Metrics and logs**
   - Expose metrics such as `seamless_sla_deadline_seconds`,
     `seamless_backfill_wait_ms`, `backfill_completion_ratio` in Prometheus.
   - Collect structured logs (e.g., `seamless.backfill.attempt`,
     `seamless.sla.downgrade`) to trace backfill and SLA events.

6. **Validation and regression tests**
   ```bash
   uv run -m pytest -W error -n auto \
     tests/qmtl/runtime/sdk/test_history_coverage_property.py \
     tests/qmtl/runtime/sdk/test_seamless_provider.py
   ```
   The suite covers coverage math and failure‑injection scenarios to validate
   SDP stability.

## 3. Complexity assessment

- **Component diversity**: multiple subsystems (store, fetch, backfill, live,
  conformance, SLA) raise the learning curve. Coordinator and artifact
  fingerprint settings require careful control under the `seamless` section of
  `qmtl.yml`.
- **Observability**: without SLAs and backfill dashboards issues are hard to
  catch early; Jsonnet dashboards and Prometheus familiarity are helpful.
- **Testing**: running the official suite is recommended; keep the `uv` based
  pipeline in CI or local development.

Overall complexity is **moderate to high** because both infrastructure
(coordinator, monitoring) and application (strategy, SLA, conformance)
configurations are required.

## 4. Usability improvements

1. **Config templates** — add YAML samples and SLA/conformance presets under
   `operations/` (include a Compose stack).
2. **Auto validation scripts** — add a health‑check CLI under `scripts/` to
   validate environment variables, coordinator connectivity, and Prometheus
   metrics exposure.
3. **Modular settings object** — introduce a dataclass to reduce constructor
   parameters and centralize strategy/SLA/fingerprint policy.
4. **Dashboard packaging** — ship Jsonnet dashboards as a Helm Chart or
   Terraform module to simplify Prometheus/Grafana rollout.

Applying the above improvements shortens initial setup time and makes it easier
to detect operational issues early.

## 5. Action items

1. **Config templates**
   - Create a new subfolder under `operations/` with example YAML, SLA/
     conformance presets, and a Compose stack.
   - Document services/variables in a README and update navigation in
     `mkdocs.yml`.

2. **Validation scripts**
   - Add a CLI in `scripts/` that checks environment, coordinator health, and
     Prometheus metrics.
   - Document usage/requirements and add an optional CI health stage.

3. **Introduce settings dataclass**
   - Encapsulate provider initialization; plan migration steps for call sites.
   - Define fields for strategy, SLA, conformance, and fingerprint policy; add
     tests.

4. **Automate dashboard packaging**
   - Build a pipeline to package Jsonnet under `operations/monitoring/` as Helm
     or Terraform artifacts with sample values.
   - Document deployment and Grafana/Prometheus integration.
