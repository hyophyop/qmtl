# Policy Engine

This guide describes how to define and apply world policies.

## Sample Policy

A sample policy using validation profiles is provided in [`sample_policy.yml`](./sample_policy.yml):

```yaml
validation_profiles:
  backtest:
    sample:
      min_effective_years: 2.0
      min_trades_total: 50
    performance:
      sharpe_min: 0.5
      max_dd_max: 0.25
      gain_to_pain_min: 1.0
    robustness:
      dsr_min: 0.15
    risk:
      adv_utilization_p95_max: 0.5
      participation_rate_p95_max: 0.4
  paper:
    sample:
      min_effective_years: 3.0
    performance:
      sharpe_min: 0.8
      max_dd_max: 0.2
      gain_to_pain_min: 1.2
    robustness:
      dsr_min: 0.25

default_profile_by_stage:
  backtest_only: backtest
  paper_only: paper

selection:
  top_k:
    metric: sharpe
    k: 3
  correlation:
    max: 0.8
  hysteresis:
    metric: sharpe
    enter: 0.6
    exit: 0.4
```

## Applying a Policy

Use the WorldService API to apply a policy and evaluate strategies:

```bash
curl -X POST /worlds/alpha/apply \
  -H 'Content-Type: application/json' \
  -d '{"policy": { ... }, "metrics": { ... }}'
```

The response contains the active strategies after evaluation.

```json
{
  "ok": true,
  "run_id": "...",
  "active": ["alpha-core", "alpha-hedge"],
  "phase": "completed"
}
```

`ok` defaults to `true`, `active` mirrors the persisted strategy roster (empty when nothing is active), and `phase` is optional—`completed` for successful runs, or another stage while the 2‑Phase apply is still progressing.
