---
title: "Migration: Removing Legacy Modes and BC Surfaces"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-04
---

{{ nav_links() }}

# Migration: Removing Legacy Modes and Backward Compatibility

This guide summarizes changes and how to migrate your code.

- Runner API: replace `Runner.backtest/dryrun/live` with `Runner.run(world_id=..., gateway_url=...)` or `Runner.offline(...)`.
- CLI: replace `qmtl sdk --mode <...>` with `qmtl sdk run --world-id <id> --gateway-url <url>` or `qmtl sdk offline`.
- Gateway `/strategies`: stop sending `run_type`; optionally include `world_id` for correlation.
- Brokerage imports: use `from qmtl.brokerage import PerShareFeeModel, VolumeShareSlippageModel` (canonical modules), not `qmtl.brokerage.simple` duplicates.

Quick check
- Search your repo for `Runner.backtest|Runner.dryrun|Runner.live|--mode|run_type`.
- Update example scripts to accept `--world-id/--gateway-url` or use `Runner.offline` for local runs.

{{ nav_links() }}

