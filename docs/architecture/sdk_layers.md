# SDK Layering Guidelines

This note summarizes the intended dependency flow inside the SDK so we avoid new import cycles and keep interfaces thin.

- Preferred direction: `foundation → protocols → core → nodes → io → strategies`.
- Protocols: keep shared interfaces like `StreamLike`, `NodeLike`, `HistoryProvider*`, `EventRecorder` under `qmtl.runtime.sdk.protocols` and depend on those instead of concrete node classes.
- Core (cache, backfill, data_io) should not import node implementations; use the shared protocols only.
- Nodes can depend on core, but avoid making core depend on nodes to prevent cycles.
