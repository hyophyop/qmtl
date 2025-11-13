# Runtime SDK Radon Cleanup Plan

## Scope
- Modules: `qmtl/runtime/sdk/activation_manager.py`, `backtest_validation.py`, `conformance.py`, `execution_context.py`, `snapshot.py`, and `qmtl/runtime/transforms/alpha_performance.py`.
- Open issues this plan will close: #1461, #1462, #1465, #1466, #1469, #1470, #1484, #1485, #1495, #1500.

## Current radon snapshot
| File | Worst CC block (grade / score) | MI | Raw SLOC | Notes |
| --- | --- | --- | --- | --- |
| `runtime/sdk/activation_manager.py` | `_on_message` — C / 19 | 21.96 (A) | 261 | Activation fan-out and gateway orchestration still sit in one method.
| `runtime/sdk/backtest_validation.py` | `validate_backtest_data` — C / 12 | 51.78 (A) | 182 | Data quality checks mix schema validation, scoring, and reporting.
| `runtime/sdk/conformance.py` | `_extract_schema_mapping` — C / 15 | 32.26 (A) | 304 | Timestamp normalization and schema extraction are tightly coupled.
| `runtime/sdk/execution_context.py` | `resolve_execution_context` — B / 10 (now A) | 76.60 (A) | 69 | Already below threshold but included because #1484 tracks the full orchestration.
| `runtime/sdk/snapshot.py` | `_record_snapshot_metrics` — B / 10 | 29.09 (A) | 437 | Metrics plumbing still shares logic with persistence.
| `runtime/transforms/alpha_performance.py` | `AlphaPerformanceNode` — A / 3 | 82.64 (A) | 78 | Remains simple but tied to #1500 for consistency with analytics helpers.

## Refactor strategy
1. **Activation fan-out** – split `_on_message` into parser, subscription matcher, and execution helpers so the orchestrator only coordinates results. Add guard clauses for early exits.
2. **Validation pipeline** – treat `BacktestDataValidator` as a series of pluggable stages (schema, ordering, timeout, scoring). Keep each stage pure and independently unit-tested.
3. **Conformance normalization** – move timestamp parsing, epoch alignment, and nan filtering into helper functions; leave `_normalize_timestamps` as the high-level coordinator.
4. **Snapshot & alpha helpers** – extract metric emission and storage concerns into decorators or helper classes so snapshot writers and alpha transforms stay ≤ B.
5. **Documentation/testing** – update architecture notes plus SDK tests so regression coverage exists before flipping radon gates.

## Validation checklist
- `uv run --with radon -m radon cc -s qmtl/runtime/sdk/{activation_manager,backtest_validation,conformance,execution_context,snapshot}.py`
- `uv run --with radon -m radon cc -s qmtl/runtime/transforms/alpha_performance.py`
- `uv run --with radon -m radon mi -s qmtl/runtime/sdk qmtl/runtime/transforms/alpha_performance.py`
- `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests qmtl/runtime/transforms/tests`
- `uv run mkdocs build`

## Expected outcome
Once these steps land, the draft PR associated with this plan will be flipped ready-for-review and will close: **Fixes #1461, Fixes #1462, Fixes #1465, Fixes #1466, Fixes #1469, Fixes #1470, Fixes #1484, Fixes #1485, Fixes #1495, Fixes #1500.**
