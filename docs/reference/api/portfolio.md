---
title: "Portfolio & Position API"
tags:
  - sdk
  - portfolio
last_modified: 2025-09-08
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
- total_value *(property)*

## Helpers

``order_value(symbol, value, price)``
: Return quantity for order worth a target notional ``value``.

``order_percent(portfolio, symbol, percent, price)``
: Size order at ``percent`` of current portfolio value.

``order_target_percent(portfolio, symbol, percent, price)``
: Reach target weight for ``symbol`` (rebalancing helper).

These helpers return signed quantities and can be combined with existing order
generation routines.

