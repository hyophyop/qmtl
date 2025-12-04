# Core Loop Contract Test Skeleton

This directory hosts the Core Loop contract test suite (T6 P0-M1). It provides a fast harness for
“submit → evaluate/activate → safe execution/gating → observe results” flows without requiring
external services by default.

- `stack.py` starts a stub WorldService + Gateway in-process (reusing the world_smoke stub) or
  reuses a pre-provisioned service stack when `WS_MODE=service` and `GATEWAY_URL`/`WORLDS_BASE_URL`
  are set.
- `conftest.py` exposes the `core_loop_stack` and `core_loop_world_id` fixtures for tests.
- `worlds/` seeds a tiny demo world into the stub stack so basic flows work out of the box.

Running locally:

```
pytest -q tests/e2e/core_loop
```

Configuration knobs:
- `CORE_LOOP_STACK_MODE`: set to `inproc` to force the stub stack, or `service` to require
  external endpoints; default `auto` prefers service when reachable, otherwise falls back to inproc.
- `CORE_LOOP_WORLD_ID` / `CORE_LOOP_WORLD_IDS`: optional world ids when using an external service.
- `CORE_LOOP_ARTIFACT_DIR`: override the artifacts directory (`.artifacts/core_loop` by default).

Contract tests:
- Marked with `@pytest.mark.contract`; CI runs them via `CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q`.
- Cover ExecutionDomain default-safe downgrade expectations (missing `as_of` downgrades to compute-only)
  and ComputeContext precedence/downgrade when WorldService decisions are unavailable.

References: docs/ko/design/core_loop_roadmap.md, docs/en/design/core_loop_roadmap_issue_drafts.md.
