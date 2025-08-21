# Unregistered Alpha Test Refactor

## Background
- Several tests hardcode alpha document paths or component lists.
- Adding or modifying alphas forces manual test updates.

## Affected Tests
1. `tests/test_list_alpha_status.py`
   - Uses fixed doc path `docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md`.
2. `strategies/tests/test_alpha_usage_tracking.py`
   - Contains hardcoded `expected_alphas` list.
3. `strategies/tests/nodes/test_composite_alpha.py`
   - Asserts component count and names explicitly.

## Tasks
- [ ] Make `test_list_alpha_status` select an implemented doc dynamically (e.g., from registry or fixture).
- [ ] Derive expected alphas in `test_alpha_usage_tracking` from `composite_alpha` or registry instead of hardcoding.
- [ ] Auto-discover `composite_alpha` component list in its tests; avoid fixed counts/names.
- [ ] Audit remaining tests for similar patterns and schedule follow-ups if needed.

### Parallelization
- Each test file can be refactored independently; assign separate owners to work in parallel.
- Audit step can run concurrently with refactors to shorten cycle time.

## Deliverables
- Updated tests with reduced maintenance cost.
- Optional fixtures/utilities to share registry-based lookup logic.
