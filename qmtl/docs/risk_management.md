# Risk Management Guide

This guide explains how to configure and use the `RiskManager` to enforce portfolio limits during backtests and simulations.

## Configuration

`RiskManager` supports several parameters to control portfolio risk:

- `max_position_size`: absolute maximum position value.
- `max_leverage`: maximum allowed leverage ratio.
- `max_drawdown_pct`: maximum tolerated drawdown as a fraction.
- `max_concentration_pct`: cap on single position concentration.
- `max_portfolio_volatility`: annualized volatility threshold.
- `position_size_limit_pct`: maximum percentage of portfolio per position.
- `enable_dynamic_sizing`: whether to automatically scale positions to meet limits.

Initialize the manager with the limits appropriate for your strategy:

```python
from qmtl.sdk.risk_management import RiskManager

risk_mgr = RiskManager(position_size_limit_pct=0.10)
```

## Enforcing Position Limits

Use `validate_position_size` to check proposed trades. It returns whether the trade is valid, any violation details, and the quantity adjusted to satisfy limits.

```python
from qmtl.examples.strategies.risk_managed_strategy import enforce_position_limit

is_valid, violation, adjusted_qty = enforce_position_limit(
    symbol="AAPL", proposed_quantity=20, price=10.0, portfolio_value=1_000.0
)
```

If the trade exceeds the configured limits, `is_valid` is `False` and `adjusted_qty` reflects the maximum safe quantity.
