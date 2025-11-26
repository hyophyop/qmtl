---
title: "Backtest Data Validation"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Backtest Data Validation

`validate_backtest_data` inspects cached history before replay to catch common quality issues. It generates a `DataQualityReport` for each `StreamInput` and can halt execution when data falls below a required threshold.

## Checks performed

- **Timestamp gaps** – missing intervals beyond a tolerance
- **Invalid prices** – non‑numeric or out‑of‑range values
- **Suspicious moves** – single‑period price changes above `max_price_change_pct`
- **Missing fields** – required OHLC fields absent or null

## Configuration

`BacktestDataValidator` accepts several options:

| Option | Description |
| --- | --- |
| `max_price_change_pct` | Maximum allowed single‑period change (default `0.1` for 10%) |
| `min_price` | Minimum acceptable price value |
| `max_gap_tolerance_sec` | Largest allowed timestamp gap in seconds |
| `required_fields` | Fields that must be present in each record |

Use `validate_backtest_data(strategy, fail_on_quality_threshold=0.8)` to enforce a minimum quality score.

Runner integration:
- For local/backtest runs, use `Runner.submit(MyStrategy, mode="backtest")` and invoke validation in your setup or pre-run checks.
- For WS-first runs, use `Runner.submit(MyStrategy, world=..., mode="paper"|"live")` and keep validation as a separate preflight step if needed.

## Example

The script at `qmtl/examples/backtest_validation_example.py` shows how to enable validation before running offline or under WS. A sample CSV with deliberate gaps is provided at `qmtl/examples/data/backtest_validation_sample.csv` for experimentation.

{{ nav_links() }}
