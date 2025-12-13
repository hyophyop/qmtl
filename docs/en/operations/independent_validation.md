# Independent Validation Operating Model

This page operationalizes **Independent Validation** into repository and CI practices. For related operational context, see [World Validation Governance](world_validation_governance.md).

## Goals

- Clarify the ownership/approval boundary between “strategy code” and “validation rules/policies”.
- On every validation rule/policy change, generate an **impact report** in CI and fail the build when thresholds are exceeded.
- Keep a minimal approval/change log format for reproducibility.

## RACI

- **Quant (Strategy)**: lead strategy changes, help reproduce failure cases
- **Validation/Risk (Independent Validation)**: approve (merge) validation rules/policies, own thresholds/override posture
- **Platform/Infra**: run CI/scheduled jobs, keep artifacts accessible and retained

Suggested SLA (default):

- Policy/rule PRs: first review within 1 business day; approve/reject decision within 2 business days

## Repository Boundaries (CODEOWNERS)

Treat the following paths as the validation rule/policy boundary and require CODEOWNERS approval in review.

- `docs/**/world/sample_policy.yml`
- `qmtl/services/worldservice/policy_engine.py`
- `qmtl/services/worldservice/validation_*.py`
- `qmtl/services/worldservice/extended_validation_worker.py`
- `scripts/policy_*.py`
- `operations/policy_diff/**`

Configuration:

- `.github/CODEOWNERS`

!!! note "Important"
    “Merge blocked without CODEOWNERS approval” is enforced only when GitHub branch protection / rulesets are enabled.  
    For private repositories under personal accounts, some protection features may be unavailable depending on the plan; consider making the repo public or moving to an org/plan that supports enforcement.

## CI Enforcement (Policy/Rule Regression Report)

When validation policy/rule boundary files change, CI runs a **base vs head** regression comparison.

- `.github/workflows/policy-diff-regression.yml`

Default scenario set:

- `operations/policy_diff/bad_strategies_runs/*.json`

Artifacts:

- base/head snapshots
- diff report (JSON/Markdown)

Failure threshold (default 5%):

- `fail_impact_ratio` (0~1)

## Change Log (Minimal)

For every validation policy/rule PR, include in the PR description:

- summary (rules/policy/metrics)
- impact scope (impact ratio, affected strategies)
- operational plan (warn→fail promotion, override/rollback plan)

## Local Rehearsal

You can rehearse the regression impact locally.

```bash
uv run python scripts/policy_snapshot.py \
  --policy docs/ko/world/sample_policy.yml \
  --runs-dir operations/policy_diff/bad_strategies_runs \
  --stage backtest \
  --output head_snapshot.json

uv run python scripts/policy_snapshot_diff.py \
  --old base_snapshot.json \
  --new head_snapshot.json \
  --fail-impact-ratio 0.05 \
  --output policy_regression_report.json \
  --output-md policy_regression_report.md
```

Generate `base_snapshot.json` from the comparison commit (e.g. `main`) using the same command.
