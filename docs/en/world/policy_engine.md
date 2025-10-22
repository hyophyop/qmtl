# Policy Engine

This guide describes how to define and apply world policies.

## Sample Policy

A sample policy is provided in [`sample_policy.yml`](./sample_policy.yml):

```yaml
thresholds:
  sharpe:
    metric: sharpe
    min: 0.5
  drawdown:
    metric: drawdown
    max: 0.2
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
