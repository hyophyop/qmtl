# Brokerage Model Assumptions

QMTL's brokerage layer keeps the initial implementation intentionally simple.
These defaults make examples runnable without large datasets while leaving clear
extension points.

- **Tick and lot sizes:** `SymbolPropertiesProvider` applies asset-class
  defaults (`0.01` tick, `1` lot for equities, etc.).  Orders are validated
  against these values and can be overridden by supplying a custom table or
  file.
- **Exchange hours & calendar:** `ExchangeHoursProvider.with_us_sample_holidays`
  offers a compact US‑equity schedule with a few holidays and an early close.
  It is not exhaustive; provide a full calendar for production use.
- **Short selling:** If no `ShortableProvider` is given, sells are assumed to be
  shortable with unlimited quantity.  Plug in `StaticShortableProvider` or a
  custom provider to enforce borrow limits and fees.
- **Slippage & fees:** Examples use `ConstantSlippageModel` and
  `PercentFeeModel` for brevity.  Swap these for more realistic models such as
  `SpreadBasedSlippageModel`, `IBKRFeeModel`, or `CompositeFeeModel`.
- **Settlement:** `SettlementModel` defaults to immediate cash movement.  To
  simulate T+N with reserved cash, enable `defer_cash=True` and pair with
  `CashWithSettlementBuyingPowerModel`.

These assumptions complement the API details in
[Brokerage API](api/brokerage.md) and the design notes in
[Lean Brokerage Model](../architecture/lean_brokerage_model.md).
