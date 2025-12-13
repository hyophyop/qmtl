# SDK ValidationPipeline Deprecation Guide

The SDK `ValidationPipeline` is kept only for local precheck (metrics) purposes. WorldService is the single source of truth (SSOT) for policy evaluation and gating. This guide describes the post-migration behavior and emergency bypass steps.

## Default behavior
- v1.5+: `ValidationPipeline` computes **metrics only** (local policy evaluation/gating removed).
- The WS evaluation outcome is the final decision; the SDK `precheck` section is informational only.

## Emergency bypass / rollback
- If WS is unstable (outage/deploy issues), use `Runner.submit(..., auto_validate=False)` to submit without validation and re-evaluate after WS stabilizes.
- For a hard rollback, pin the SDK version to a known-good release prior to the change.

## Recommended usage
- In submission/test pipelines, surface WS results (`SubmitResult.ws.*`) as the primary output; keep `precheck` in a separate section.
- If SDK vs WS results diverge, prioritize WS logs/metrics; use `precheck` only as a debugging hint.

## Rollout (recommended)
- Order: **Backtest → Paper → Live**
- Validate at each stage:
  - `SubmitResult.ws.*` is populated (decision/activation/evaluation_run_url)
  - `/worlds/{id}/evaluate` 4xx/5xx, latency, and fail-closed rate
  - Alerts for WS/ControlBus/worker paths (operations dashboards)

## Checklist (DoD)
- The WS single-entry contract is locked by tests (rule execution/error handling, etc.).
- This deprecation guide ships together with clear rollout/rollback guidance.
