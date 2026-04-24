---
title: "Portfolio & Position API"
tags:
  - sdk
  - portfolio
last_modified: 2026-04-24
---

{{ nav_links() }}

# Portfolio & Position API

This document outlines a high-level Portfolio/Position API and helper functions for expressing orders as portfolio weights or values.

## Objects

Position
- symbol: ``str``
- quantity: ``float``
- avg_cost: ``float``
- market_price: ``float``
- market_value: ``float`` *(property)*
- unrealized_pnl: ``float`` *(property)*

Portfolio
- cash: ``float``
- positions: ``Dict[str, Position]``
- get_position(symbol) -> ``Position | None``
- apply_fill(symbol, quantity, price, commission=0.0)
- total_value *(property)*: Aggregates positions using each holding's
  ``market_price``. For sizing at a newly observed price, either mark the
  relevant position(s) to that price first or use a helper that computes
  with mark-to-market adjustments.

## Helpers

``order_value(symbol, value, price)``
: Return quantity for order worth a target notional ``value``.

``order_percent(portfolio, symbol, percent, price)``
: Size order at ``percent`` of current portfolio value.

``order_target_percent(portfolio, symbol, percent, price)``
: Reach target weight for ``symbol`` (rebalancing helper).

These helpers return signed quantities and can be combined with existing order
generation routines.

## Local PnL Diagnostics

For fast local strategy iteration, callers can opt into
`qmtl.runtime.sdk.diagnostics.summarize_account_pnl`. The helper accepts local
fills plus optional mark prices and returns account-level `ending_cash`,
`equity`, `realized_pnl`, `unrealized_pnl`, `fees`, `total_pnl`, and open
position summaries.

```python
from qmtl.runtime.sdk.diagnostics import AccountFill, summarize_account_pnl

summary = summarize_account_pnl(
    [
        AccountFill("AAPL", 10, 100.0, commission=1.0),
        AccountFill("AAPL", -4, 110.0, commission=0.5),
    ],
    marks={"AAPL": 120.0},
    starting_cash=1_000.0,
)

assert summary.total_pnl == 158.5
```

This surface is an opt-in local iteration aid. It does not change
`Runner.submit(..., world=...)`, Gateway/WorldService, or the portfolio/risk
hub authority model.
