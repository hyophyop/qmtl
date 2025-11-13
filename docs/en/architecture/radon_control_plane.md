# Control-Plane Radon Plan (Gateway + DAG Manager)

## Scope
- Modules: `qmtl/services/gateway/{controlbus_consumer,shared_account_policy,strategy_submission.py}`, `strategy_manager.py`, and `qmtl/services/dagmanager/{diff_service.py,grpc_server.py}`.
- Planned issue closures: #1471, #1472, #1473, #1475, #1477, #1488, #1496, #1497.

## Current radon snapshot
| File | Worst CC block (grade / score) | MI | Raw SLOC | Notes |
| --- | --- | --- | --- | --- |
| `services/gateway/controlbus_consumer.py` | `_parse_kafka_message` — C / 15 | 24.61 (A) | 338 | Parsing, validation, and dispatch logic still mingle.
| `services/gateway/shared_account_policy.py` | `_accumulate_notional` — B / 9 | 35.19 (A) | 163 | Mostly compliant but participates in #1496 as shared policy glue.
| `services/gateway/strategy_submission.py` | `_build_queue_outputs` — C / 14 | 30.66 (A) | 245 | Submission helper still handles persistence + queue wiring.
| `services/gateway/strategy_manager.py` | `_inject_version_sentinel` — B / 7 | 24.61 (A) | 345 | Kept for completeness across the gateway meta-issue.
| `services/dagmanager/diff_service.py` | `_hash_compare` — C / 20 | 0.00 (C) | 906 | Large streaming helpers cause MI to crater.
| `services/dagmanager/grpc_server.py` | `GetQueueStats` — C / 17 | 24.73 (A) | 348 | `DiffServiceServicer.Diff` now B but other RPC handlers remain complex.

## Refactor strategy
1. Normalize gateway control flow by isolating request parsing, validation, and effectful operations (storage, queue writes) into separate helpers orchestrated by thin async functions.
2. Introduce shared policy/strategy dataclasses so both `StrategySubmissionHelper` and `StrategyManager` reuse the same validation logic instead of copy/pasting branches.
3. Refactor diff streaming into a pipeline (queue poll ➜ diff calculation ➜ stream write ➜ bus publish) with explicit helper coroutines to lift nesting and improve MI.
4. Extend DAG/gateway integration tests to cover failure + retry paths before finalizing the refactor.

## Validation checklist
- `uv run --with radon -m radon cc -s qmtl/services/gateway/{controlbus_consumer,shared_account_policy,strategy_submission,strategy_manager}.py`
- `uv run --with radon -m radon cc -s qmtl/services/dagmanager/{diff_service,grpc_server}.py`
- `uv run --with radon -m radon mi -s qmtl/services/dagmanager/diff_service.py`
- `uv run -m pytest -W error -n auto qmtl/services/gateway/tests qmtl/services/dagmanager/tests`

## Expected outcome
The final implementation PR based on this plan will close: **Fixes #1471, Fixes #1472, Fixes #1473, Fixes #1475, Fixes #1477, Fixes #1488, Fixes #1496, Fixes #1497.**
