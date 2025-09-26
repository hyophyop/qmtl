# CCXT × Seamless Integrated Blueprint – Implementation Gaps

The following backlog captures implementation deltas between the published architecture and the current codebase. Each item links the blueprint requirement to the source modules that need follow-up work.

## Work Items

1. **Extend CCXT rate limiter configuration and enforcement**  
   The blueprint expects Redis token bucket settings with `tokens_per_interval`, `interval_ms`, `burst_tokens`, `local_semaphore`, and a `penalty_backoff_ms` cooldown after HTTP 429 responses.【F:docs/architecture/ccxt-seamless-integrated.md†L140-L148】【F:docs/architecture/ccxt-seamless-integrated.md†L405-L413】  
   `RateLimiterConfig` and `get_limiter` currently expose only per-second tokens and lack any penalty/backoff integration, so CCXT fetchers cannot honor the documented knobs.【F:qmtl/runtime/io/ccxt_fetcher.py†L24-L56】【F:qmtl/runtime/io/ccxt_rate_limiter.py†L1-L202】

2. **Align backfill coordinator configuration names and jitter semantics**  
   The YAML contract lists `max_attempts`, `retry_backoff_ms`, and `jitter_ratio` under `seamless.backfill`, but `BackfillConfig` still exposes `retry_max`, `retry_base_backoff_ms`, and a boolean `retry_jitter`, making the documented settings ineffective.【F:docs/architecture/ccxt-seamless-integrated.md†L396-L404】【F:qmtl/runtime/sdk/seamless_data_provider.py†L155-L166】

3. **Add structured logging for backfill attempt, completion, and failure**  
   Operations guidance calls for per-batch attempt/complete/fail logs to feed dashboards, yet `DataFetcherAutoBackfiller` only logs starts and warnings on storage fallback, omitting success/failure events.【F:docs/architecture/ccxt-seamless-integrated.md†L130-L135】【F:qmtl/runtime/io/seamless_provider.py†L86-L156】

4. **Include fingerprint/as-of context in domain downgrade logs**  
   Governance rules require every downgrade to reference the governing `{dataset_fingerprint, as_of}` pair, but `seamless.domain_gate.downgrade` logs emit only node/domain identifiers and the reason.【F:docs/architecture/ccxt-seamless-integrated.md†L321-L344】【F:qmtl/runtime/sdk/seamless_data_provider.py†L947-L957】

5. **Ensure artifact manifests always carry provenance metadata**  
   Manifests are supposed to record producer identity and the publication watermark even in development, but the default `ArtifactRegistrar` returns manifests without those fields and the Enhanced provider falls back to a registrar with `stabilization_bars=0`, bypassing the documented tail-bar drop.【F:docs/architecture/ccxt-seamless-integrated.md†L241-L289】【F:qmtl/runtime/io/artifact.py†L21-L139】【F:qmtl/runtime/io/seamless_provider.py†L268-L295】

6. **Implement fingerprint publication toggles**  
   The architecture introduces `publish_fingerprint` and `early_fingerprint` switches, but the runtime only supports a legacy/canonical mode flag and does not expose the documented toggles to ingestion workers.【F:docs/architecture/ccxt-seamless-integrated.md†L263-L281】【F:qmtl/runtime/sdk/seamless_data_provider.py†L320-L338】

7. **Emit `as_of_advancement_events` metric**  
   The metrics catalog mandates a counter for monotonic `as_of` promotions, yet `qmtl/runtime/sdk/metrics.py` defines no such series, so downstream alerts cannot be configured.【F:docs/architecture/ccxt-seamless-integrated.md†L503-L524】【F:qmtl/runtime/sdk/metrics.py†L150-L290】

8. **Surface coordinator lifecycle logs**  
   The operations checklist calls for structured claim/complete/fail logs from the distributed coordinator, but the HTTP client only logs warning paths and never records successful transitions, leaving the documented dashboards blind.【F:docs/architecture/ccxt-seamless-integrated.md†L500-L502】【F:qmtl/runtime/sdk/backfill_coordinator.py†L58-L136】

