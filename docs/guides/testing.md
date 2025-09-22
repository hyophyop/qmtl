---
title: "Testing & Pytest Conventions"
tags:
  - guide
  - testing
  - pytest
author: "QMTL Team"
last_modified: 2025-09-08
---

# Testing & Pytest Conventions

This guide documents how we structure tests, run them efficiently, and avoid common pitfalls when working with pytest in QMTL.

## Python & Environment

- Use `uv` to manage Python and dependencies.
- Project Python: `>=3.11`. Pin locally to ensure consistency:
  - `uv python install 3.11`
  - `uv python pin 3.11`
  - `uv pip install -e .[dev]`

## Fast Preflight (hang detection)

Run a quick preflight before the full suite to surface hangs early. This converts long-running tests into failures with a traceback.

- Hang preflight:
  - `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`
- Optional collection-only sanity check:
  - `uv run -m pytest --collect-only -q`
- Full suite (parallel):
  - `uv run -m pytest -W error -n auto`

Notes for authors:
- If a test is expected to exceed 60s, add an override: `@pytest.mark.timeout(180)`.
- Mark intentionally long or external-dependency tests as `slow` and exclude from preflight via `-k 'not slow'` when needed.
- Prefer deterministic, dependency‑free tests; avoid unbounded network waits.

## Pytest plugins: top‑level only

Pytest 8 removed support for defining `pytest_plugins` in non‑top‑level `conftest.py`. To ensure compatibility:

- Only define `pytest_plugins = (...)` in the repository’s top‑level `conftest.py`.
- Do not set `pytest_plugins` in nested `conftest.py` files (e.g., under `tests/` subpackages). Those files should only contain local fixtures and helpers.
- If you need to share fixtures across a test subtree, place them in a normal module (e.g., `tests/e2e/world_smoke/fixtures_inprocess.py`) and register them from the root `conftest.py`:

```python
# conftest.py (repository root)
pytest_plugins = (
    "tests.e2e.world_smoke.fixtures_inprocess",
    "tests.e2e.world_smoke.fixtures_docker",
)
```

Why this matters: when pytest is invoked, only the top‑level `conftest.py` relative to the test root may define `pytest_plugins`. Non‑top‑level declarations are ignored (and now error), causing missing fixtures at collection time.

Tips:
- Always run pytest from the repository root (which contains `pytest.ini`). Pytest will detect the rootdir and load the top‑level `conftest.py`.
- If running from a subdirectory, pytest still discovers the repo root via `pytest.ini`; if you step outside the repo, pass `-c path/to/pytest.ini` to keep the correct root.

## Markers and parallelism

- Run tests in parallel with `pytest-xdist` (`-n auto`) for faster feedback.
- For suites with shared resources, use `--dist loadscope` or cap workers (e.g., `-n 2`). Mark strictly serial tests and run them separately.

## Shared node factories

Gateway and SDK tests rely on consistent node hashing. Reuse the helpers in
`tests/factories/node.py` rather than hand-rolling node dictionaries. The
factories canonicalise parameters, sort dependencies, and compute `node_id`
values so hash-contract updates only need to change in one place.

```python
from tests.factories import tag_query_node_payload, node_ids_crc32

node = tag_query_node_payload(tags=["t"], interval=60)
checksum = node_ids_crc32([node])
```

