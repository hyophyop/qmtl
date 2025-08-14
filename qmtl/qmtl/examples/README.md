# QMTL Strategy Project

This README serves as a template for projects created with `qmtl init`.
It outlines basic setup and testing instructions.

## Setup

```bash
uv venv
uv pip install -e qmtl[dev]
```

## Testing

Run the test suite and treat warnings as errors:

```bash
uv run -m pytest -W error
```

## Directory Layout

- `nodes/` – node processor implementations.
- `dags/` – strategy DAG definitions.
- `tests/` – unit tests for nodes and DAGs.

Customize this file with project-specific details.
