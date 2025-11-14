# WorldService Allocation & Rebalancer Radon Plan

## Scope
- Modules: `qmtl/services/worldservice/services.py`, `worldservice/rebalancing/multi.py`, `worldservice/storage/persistent.py`.
- Planned issue closures: #1478, #1479, #1489, #1498.

## Current radon snapshot
| File | Worst CC block (grade / score) | MI | Raw SLOC | Notes |
| --- | --- | --- | --- | --- |
| `services/worldservice/rebalancing/multi.py` | `_derive_strategy_targets` — C / 13 | 53.85 (A) | 122 | Multi-world proportional logic still couples validation, math, and storage calls.
| `services/worldservice/services.py` | `_handle_existing_allocation_run` — B / 7 | 27.30 (A) | 374 | The orchestrator shrank but still mixes validation, locking, and persistence.
| `services/worldservice/storage/persistent.py` | `create` / `add_policy` — B / 7 | 13.39 (B) | 1 047 | Storage helper exceeds soft SLOC limits and drags MI near the floor.

## Refactor strategy
1. Model allocation updates as explicit stages (payload normalization, plan synthesis, persistence, execution) handled by focused helpers; let `WorldService.upsert_allocations` orchestrate those stages only.
2. Move proportional rebalancing math into reusable calculators so `MultiWorldProportionalRebalancer.plan` simply wires inputs/outputs and stays ≤ B.
3. Split `PersistentStorage` into targeted repositories (world metadata, policies, allocations) or at least move large methods into standalone helpers to lift MI above 20.
4. Expand unit/integration tests around allocation plans and storage mutations to cover the new seams before we lower radon budgets.

## Validation checklist
- `uv run --with radon -m radon cc -s qmtl/services/worldservice/{services,rebalancing/multi}.py`
- `uv run --with radon -m radon mi -s qmtl/services/worldservice/storage/persistent.py`
- `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests`
- `uv run mkdocs build`

## Expected outcome
The draft PR informed by this plan will ultimately merge with the allocation/refactor changes and close: **Fixes #1478, Fixes #1479, Fixes #1489, Fixes #1498.**
