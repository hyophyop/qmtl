# Seamless Data Provider modularization memo

## Overview
The Seamless data provider had accumulated SLA handling, domain policies, backfill orchestration, and range math in a single class. The refactor slices those responsibilities into helper modules so we can hit our Radon CC/MI targets and let multiple engineers work in parallel.

Goals addressed in this change:

- **Domain gating separation** – `_DomainGateEvaluator` owns execution-domain rules.
- **Simplified availability flow** – `_AvailabilityPipeline` handles gap detection and backfill triggering, shrinking `ensure_data_available`.
- **Layered seamless fetch** – `_SeamlessFetchPlanner` coordinates per-source coverage, fetch, and backfill.
- **Reusable range math** – `_RangeOperations` centralizes merge/intersect/subtract logic.

## `_DomainGateEvaluator`
- Splits live/shadow as-of monotonicity checks from coverage/freshness enforcement.
- Uses `_merge_decisions` to combine HOLD outcomes when as-of regresses.
- Validates backtest/dry-run artifacts and `as_of` requirements in a dedicated method.
- Emits metrics (`observe_as_of_advancement_event`) and downgrade logs inside the helper so the caller stays lean.

## `_AvailabilityPipeline`
- Orchestrates coverage observation → gap computation → SLA sync-gap guard → backfill execution → post-check in a single flow.
- Wraps coordinator lease claim/complete/fail paths to isolate exception handling.
- Raises `SeamlessSLAExceeded` or delegates to `_SLATracker.handle_violation` from one place.

## `_SeamlessFetchPlanner`
- Abstracts per-source coverage probing and fetching via `_consume_source`.
- Updates remaining gaps with `_RangeOperations.subtract` to preserve interval alignment.
- Falls back to `_execute_backfill_range` when no source can serve the outstanding window and normalizes results with `pd.concat`.

## `_RangeOperations`
- Provides canonical implementations for merge, intersection, and subtraction.
- Keeps separate paths for interval-aware and interval-agnostic subtraction to match legacy behaviour.

## Test strategy
- Added unit coverage in `tests/qmtl/runtime/sdk/test_seamless_provider.py` for the new pipeline code paths.
- Focused on boundary cases that exercise `_RangeOperations` subtraction rules.
- Core suites continue to run under `uv run -m pytest -W error -n auto`.

## Follow-up
- Track performance work for `_SeamlessFetchPlanner` under issues #1482 and #1491.
- Plan to extend helper-specific unit tests and evaluate replacing `_find_missing_ranges` once confidence grows.
