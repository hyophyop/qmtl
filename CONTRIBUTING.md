# Contributing to QMTL

Please verify AlphaDocs remain in sync with the registry and module annotations before committing:

```bash
uv run scripts/check_doc_sync.py
```

Run the script from the repository root and fix any reported issues.

## Python and Tooling

- Use `uv` to manage Python and dependencies for all tasks.
- Required Python: `>=3.11`. Pin the local project to Python 3.11 to ensure consistent behavior:

```bash
uv python install 3.11
uv python pin 3.11
uv pip install -e .[dev]
```

- Run tests via `uv run` so the pinned interpreter is used:

```bash
uv run -m pytest -W error -n auto
```

If `pytest-xdist` is missing, install it with:

```bash
uv pip install pytest-xdist
```

## Testing Conventions

- Fast preflight (hang detection) before running the full suite:

  ```bash
  PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q \
    --timeout=60 --timeout-method=thread --maxfail=1
  ```

  - Optional: `uv run -m pytest --collect-only -q` to catch import-time issues.
  - After preflight: `uv run -m pytest -W error -n auto` for the full run.

- Pytest plugins must be registered only in the repository top-level `conftest.py`:

  ```python
  # conftest.py (repo root)
  pytest_plugins = (
      "tests.e2e.world_smoke.fixtures_inprocess",
      "tests.e2e.world_smoke.fixtures_docker",
  )
  ```

  Do not declare `pytest_plugins` in nested `conftest.py` files; pytest 8 rejects non-top-level declarations. If you need shared fixtures for a subtree, put them in a normal module and register from the root `conftest.py` as above.

## HTTPX Usage (tests and examples)

QMTL targets httpx 0.28.x. To avoid regressions across environments:

- The project pins `httpx>=0.28,<0.29` in `pyproject.toml`.
- In asynchronous tests using ASGI apps, always use the context-managed `ASGITransport` introduced in 0.28:

```python
async with httpx.ASGITransport(app=app) as transport:
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status")
```

- Do not instantiate `ASGITransport(app)` without a context manager, and do not call `aclose()` manually on the transport; the context handles cleanup.
- For backend stubs, prefer `httpx.MockTransport` over ad-hoc servers.

## Network and Asynchronous Operations

Use explicit state polling or event-driven communication instead of unconditional `sleep` calls or arbitrary timeouts in network or asynchronous code. Utilities such as `asyncio.wait_for` and `asyncio.Event.wait` help manage these workflows:

```python
await asyncio.wait_for(event.wait(), timeout=5)
```

## Documentation

When adding new markdown files under `docs/`, copy `docs/templates/template.md` and update the front matter fields (`title`, `tags`, `author`, `last_modified`).
