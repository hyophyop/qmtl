# QMTL Example Assets

This directory contains repository example assets used for reference and tests.
It is not a user-facing scaffold.

The public strategy-author scaffold is now:

```bash
qmtl init <path>
```

That scaffold centers on `strategies/my_strategy.py` plus `qmtl submit`.
Treat the files here as example modules you can read or adapt, not as an
alternate project layout.

## Setup

```bash
uv venv
uv pip install -e qmtl[dev]
```

## Using with the public scaffold

Create a project with `qmtl init <path>`, edit `strategies/my_strategy.py`, and
submit it through the public CLI:

```bash
qmtl submit --output json
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

## Layout

- `strategies/` contains example strategy modules used by docs and tests.
- `scripts/` contains helper/demo scripts for local operator workflows.
- `docs/` contains reference notes for example flows such as world gating.
