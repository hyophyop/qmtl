# SDK Layering Guidelines

## 0. Purpose and Core Loop Position

- Purpose: Summarise the intended dependency flow inside the SDK so we avoid new import cycles and keep interfaces thin.
- Core Loop position: Supports all Core Loop stages (submit, warm‑up, evaluation, activation) by ensuring they run on a **well‑defined SDK layering scheme**; the primary audience is SDK maintainers.

This note summarizes the intended dependency flow inside the SDK so we avoid new import cycles and keep interfaces thin.

- Preferred direction: `foundation → protocols → core → nodes → io → strategies`.
- Protocols: keep shared interfaces like `StreamLike`, `NodeLike`, `HistoryProvider*`, `EventRecorder` under `qmtl.runtime.sdk.protocols` and depend on those instead of concrete node classes.
- Core (cache, backfill, data_io) should not import node implementations; use the shared protocols only.
- Nodes can depend on core, but avoid making core depend on nodes to prevent cycles.

## Validation

- Import cycles: `uv run --with grimp python scripts/check_import_cycles.py --baseline scripts/import_cycles_baseline.json`
- Layer guard (core/io/seamless → nodes): `uv run --with grimp python scripts/check_sdk_layers.py`
