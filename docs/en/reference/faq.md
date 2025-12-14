---
title: "FAQ"
tags: []
author: "QMTL Team"
last_modified: 2025-09-05
---

{{ nav_links() }}

# FAQ

## How do tag-based nodes behave under world-driven execution?

`TagQueryNode` refreshes its queue list through the `TagQueryManager` that the
Runner spawns. When a strategy runs in world-driven mode
(`Runner.submit(world=...)`) the manager performs the initial
queue lookup and establishes the WebSocket subscription. If Gateway or
WorldService are unreachable the strategy remains in the safe baseline
(compute-only, order gate OFF). `Runner.submit()` runs locally without the
Gateway; tag-based nodes start with an empty queue list in that mode.

See [Migration: Removing Legacy Modes and Backward Compatibility](../guides/migration_bc_removal.md) for guidance on updating code that previously used legacy entry points.

## My tests sometimes hang or leak resources. How can I prevent that?

- Clean up background services at the end of each test:
  - `async with Runner.session(...):` automatically disposes the `TagQueryManager`
    and `ActivationManager`.
  - Otherwise call `Runner.shutdown(strategy)` or
    `await Runner.shutdown_async(strategy)` manually.
- Apply conservative timeouts:
  - Setting `test.test_mode: true` in `qmtl.yml` shrinks the SDK's default HTTP/WS
    timeouts, which reduces the chance of hangs.
- Release ASGI/transport resources explicitly:
  - Wrap FastAPI apps with `async with httpx.ASGITransport(app) as transport:` and
    perform calls through `async with httpx.AsyncClient(transport=transport, ...)`.
  - The Gateway app offers `create_app(enable_background=False)` to avoid spawning
    background tasks. Disabling them in unit tests helps minimize contention and
    warnings.

{{ nav_links() }}
