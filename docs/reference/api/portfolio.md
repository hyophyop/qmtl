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
- symbol: str
- quantity: int
- avg_cost: float
- market_price: float
- market_value: float (property)
- unrealized_pnl: float (property)

Portfolio (conceptual)
- cash: float
- positions: Dict[str, Position]
- get_position(symbol) -> Position | None

## Helpers

order_value(symbol, value): place order worth a target notional value.
order_percent(symbol, percent): place order sized at percent of current portfolio value.
order_target_percent(symbol, percent): reach target weight for symbol (rebalancing helper).

These helpers are intended for strategy-level ergonomics and should integrate with the existing order/exec model.

