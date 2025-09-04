# Contributing to QMTL

Please verify AlphaDocs remain in sync with the registry and module annotations before committing:

```bash
uv run scripts/check_doc_sync.py
```

Run the script from the repository root and fix any reported issues.

## Network and Asynchronous Operations

Use explicit state polling or event-driven communication instead of unconditional `sleep` calls or arbitrary timeouts in network or asynchronous code. Utilities such as `asyncio.wait_for` and `asyncio.Event.wait` help manage these workflows:

```python
await asyncio.wait_for(event.wait(), timeout=5)
```

## Documentation

When adding new markdown files under `docs/`, copy `docs/templates/template.md` and update the front matter fields (`title`, `tags`, `author`, `last_modified`).
