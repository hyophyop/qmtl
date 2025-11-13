# Seamless Data Provider Radon Plan

## Scope
- Module: `qmtl/runtime/sdk/seamless_data_provider.py` (constructor, domain gate, fetch orchestration, range subtraction).
- Planned issue closures: #1468, #1482, #1491.

## Current radon snapshot
| File | Worst CC block (grade / score) | MI | Raw SLOC | Notes |
| --- | --- | --- | --- | --- |
| `runtime/sdk/seamless_data_provider.py` | `__init__` — D / 21 (E-range previously) | 0.00 (C) | 2 719 | Constructor blends config loading, SLA resolution, fingerprints, and domain gate wiring.

## Refactor strategy
1. Pull config/preset resolution into `_build_conformance_defaults`, `_init_backfill_policy`, and `_configure_fingerprint_mode` helpers so `__init__` retains orchestration only.
2. Introduce a `DomainGateEvaluator` factory that accepts dependencies via dataclasses instead of capturing `self` state everywhere.
3. Split `_fetch_seamless` into fetch-plan calculation, artifact selection, and reconciliation helpers with deterministic unit tests per stage.
4. Document the pipeline so cache/storage/backfill/live fallbacks are explicit and easier to extend.

## Validation checklist
- `uv run --with radon -m radon cc -s qmtl/runtime/sdk/seamless_data_provider.py`
- `uv run --with radon -m radon mi -s qmtl/runtime/sdk/seamless_data_provider.py`
- `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests/test_seamless_data_provider.py`
- `uv run mkdocs build`

## Expected outcome
When the draft PR based on this plan merges, it will close: **Fixes #1468, Fixes #1482, Fixes #1491.**
