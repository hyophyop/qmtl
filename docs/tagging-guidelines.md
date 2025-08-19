# Tagging Guidelines

To ensure consistent metadata across strategy components, every node module must define a module-level `TAGS` dictionary. This dictionary is used by tooling and CI to categorize outputs and facilitate discovery.

## Required Keys

- `scope`: one of `generator`, `indicator`, `signal`, `performance`, or `portfolio`.
- `family`: identifier for the underlying method or concept (e.g. `rsi`, `ema`, `volatility`).
- `interval`: sampling interval expressed as `1m`, `5m`, `1h`, or `1d`.
- `asset`: target ticker or universe name.

## Recommended Keys

- `window`: lookback window or period.
- `price`: price field used when applicable.
- `side`: `long` or `short`.
- `target_horizon`: forward looking horizon for labels or targets.
- `label`: description for supervised learning outputs.

## Formatting Rules

- All keys and string values must be lowercase.
- Values may be strings or numbers, but lists are not allowed.
- Intervals are normalized; for example `60s` is rewritten to `1m`.

## Example

```python
TAGS = {
    "scope": "indicator",
    "family": "rsi",
    "interval": "1m",
    "asset": "btc",
    "window": 14,
}
```

Use `qmtl taglint` or `python -m qmtl.tools.taglint`, or the pre-commit hook,
to validate and auto-fix tags.

## CI Alignment

Run the same checks locally that GitHub CI executes to catch errors early:

```bash
uv run qmtl taglint strategies
uv run -m pytest qmtl/tests/tools/test_taglint.py -W error
```

Ensure these commands succeed before pushing your changes.
