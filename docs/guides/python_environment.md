# Python Environment

This project standardizes on Python 3.11 and the `uv` package manager to ensure consistent behavior across development machines and CI.

- Required version: Python >= 3.11
- Manager: `uv` (fast, reproducible Python and dependency management)

## Quickstart

```bash
# Install and pin Python 3.11 for this project
uv python install 3.11
uv python pin 3.11

# Install dev dependencies in editable mode
uv pip install -e .[dev]

# Run tests in parallel using the pinned interpreter
uv run -m pytest -W error -n auto
```

## Notes

- The project’s `pyproject.toml` sets `requires-python = ">=3.11"`.
- Prefer `uv run` for all commands (tests, tools) so the pinned interpreter is used consistently.
- For faster feedback, run tests in parallel (`-n auto`). Install `pytest-xdist` if missing: `uv pip install pytest-xdist`.
- CI should also run with Python 3.11 to minimize environment drift.
