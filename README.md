# qmtl

## End-to-End Testing

For instructions on spinning up the entire stack and running the e2e suite, see [docs/e2e_testing.md](docs/e2e_testing.md).

## Running the Test Suite

Run all unit and integration tests with:

```bash
uv run pytest -q tests
```

## SDK Tutorial

For instructions on implementing strategies with the SDK, see
[docs/sdk_tutorial.md](docs/sdk_tutorial.md).

## Optional Extensions

Install additional indicator, stream, or generator packages only when needed:

```bash
uv pip install -e .[indicators]
uv pip install -e .[streams]
uv pip install -e .[generators]
uv pip install -e .[transforms]
```

## Backfills

Learn how to preload historical data using BackfillSource objects in
[docs/backfill.md](docs/backfill.md).

