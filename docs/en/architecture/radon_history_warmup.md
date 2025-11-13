# History Warmup Radon Plan

## Scope
- Module: `qmtl/runtime/sdk/history_warmup_service.py` (warmup orchestration, replay, strict-mode enforcement).
- Planned issue closures: #1467, #1487, #1492.

## Current radon snapshot
| File | Worst CC block (grade / score) | MI | Raw SLOC | Notes |
| --- | --- | --- | --- | --- |
| `runtime/sdk/history_warmup_service.py` | `_plan_strategy_warmup` — C / 15 | 11.78 (B) | 517 | Replay helpers improved, but planning still exceeds the B target.

## Refactor strategy
1. Extract plan-construction steps (window resolution, cache hit detection, node readiness) into helper objects so `_plan_strategy_warmup` orchestrates only sequencing.
2. Keep `replay_history` pathways incremental by pulling timestamp batching, retry, and metrics into pure helpers with deterministic unit tests.
3. Surface the warmup state machine in documentation so future contributors can reason about prerequisites vs. replay vs. enforcement.

## Validation checklist
- `uv run --with radon -m radon cc -s qmtl/runtime/sdk/history_warmup_service.py`
- `uv run --with radon -m radon mi -s qmtl/runtime/sdk/history_warmup_service.py`
- `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests/test_history_warmup_service.py`
- `uv run mkdocs build`

## Expected outcome
Merging the final implementation PR will automatically close: **Fixes #1467, Fixes #1487, Fixes #1492.**
