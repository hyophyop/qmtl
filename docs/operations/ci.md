# CI Environment

Continuous Integration runs on Python 3.11 via uv-managed virtualenvs. Tests run with warnings treated as errors to catch resource leaks early.

- Python: 3.11 (managed by `uv python install 3.11` + `uv venv`)
- Dependency install: `uv pip install -e .[dev]`
- Protobuf generation: `uv run python -m grpc_tools.protoc ...`
- Tests: `PYTHONPATH=qmtl/proto uv run pytest -W error -q tests`

See `.github/workflows/ci.yml` for the authoritative configuration.
