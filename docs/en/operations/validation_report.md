# Validation Report (Standard Template)

To share and retain World Validation outcomes from an ops/risk perspective, generate a **standard Validation Report** from an `EvaluationRun` payload and a Model Card.

## How to generate

- Inputs: EvaluationRun payload (JSON/YAML), Model Card payload (JSON/YAML)
- Output: Markdown (`.md`)

Example:

```bash
uv run python scripts/generate_validation_report.py \
  --evaluation-run artifacts/evaluation_run.json \
  --model-card model_cards/my_strategy.json \
  --output validation_report.md
```

## What the report includes (summary)

The generator (`scripts/generate_validation_report.py`) emits:

- Summary (status/recommended stage/policy_version/ruleset_hash)
- Scope & Objective (from Model Card)
- Rule outcomes (core + extended layers)
- Metrics snapshot (selected metrics summary)
- Override information (when present)
- Limitations & recommendations

## Related

- Evaluation Store: `operations/evaluation_store.md`
- Observability (SLO/alerts): `operations/world_validation_observability.md`

