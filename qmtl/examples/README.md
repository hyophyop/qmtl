# QMTL Strategy Project

This README serves as a template for projects created with `qmtl project init`.
It outlines basic setup and testing instructions.

## Setup

```bash
uv venv
uv pip install -e qmtl[dev]
```

## Running

Run strategies against a Gateway-connected WorldService. The Gateway will
propagate activation envelopes that include the new freeze/drain flags, so
orders remain gated off until WorldService promotes the world into a runnable
execution domain:

```bash
python strategies/my_strategy.py --world-id demo --gateway-url http://localhost:8000
```

For quick offline execution, omit the flags:

```bash
python strategies/my_strategy.py
```

### WorldService gating quickstart

Recent releases introduced two-phase apply and per-world gating policies. The
example project ships with a minimal policy document at
`worldservice/gating_policy.example.yml` and a helper CLI for driving the
apply endpoint:

```bash
python -m qmtl.examples.scripts.worldservice_apply_demo --world-id demo --dry-run
```

Drop the `--dry-run` flag to post the payload to a locally running
WorldService instance. The script surfaces the payload in JSON so you can
inspect the generated `run_id`, metrics map, and parsed gating policy before
submitting it.

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
