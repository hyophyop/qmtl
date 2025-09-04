# QMTL Strategy Project

This README serves as a template for projects created with `qmtl init`.
It outlines basic setup and testing instructions.

## Setup

```bash
uv venv
uv pip install -e qmtl[dev]
```

## Running

Run strategies against a Gateway-connected world service:

```bash
python strategies/my_strategy.py --world-id demo --gateway-url http://localhost:8000
```

For quick offline execution, omit the flags:

```bash
python strategies/my_strategy.py
```

## Testing

Run the test suite in parallel and treat warnings as errors:

```bash
uv run -m pytest -W error -n auto
```

## Directory Layout

- `nodes/` – node processor implementations.
- `dags/` – strategy DAG definitions.
- `tests/` – unit tests for nodes and DAGs.

Customize this file with project-specific details.
