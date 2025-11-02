---
title: "Lean Brokerage Model - Integration Guide"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Lean Brokerage Model - Integration Guide

## Related Documents
- [Architecture Overview](README.md)
- [QMTL Architecture](architecture.md)
- [Gateway](gateway.md)
- [DAG Manager](dag-manager.md)
- [WorldService](worldservice.md)

---

## 1. What the Lean Brokerage Model Provides

Lean bundles broker specific reality models into a single **Brokerage Model**. When
assigned to a security it injects coordinated implementations for:

- Fill quality, slippage, transaction fees, and settlement rules
- Buying power, leverage limits, and margin interest calculations
- Short availability and borrow costs
- Security metadata such as tick size, lot size, and contract multiplier
- Exchange hours, calendar exceptions, and order eligibility checks
- Pre trade validation hooks (`CanSubmitOrder`, `CanExecuteOrder`) and account type
  defaults (cash vs. margin, required free buying power)

Setting `InteractiveBrokersBrokerageModel`, for example, applies Interactive
Brokers fee schedules, leverage rules, supported markets, trading sessions, and
all subordinate models as a cohesive profile.[3]

---

## 2. Capability Blocks (Lean Reality Modeling)

Combine the following capability blocks to reproduce Lean's brokerage realism in
another platform.

### A. Pre Trade Validation and Security Metadata

- **IBrokerageModel interface** - exposes account type, `RequiredFreeBuyingPowerPercent`,
  and broker specific validation through `CanSubmitOrder` / `CanExecuteOrder`.[1][2]
- **Order properties and Time in Force** - defines GTC, GTD, IOC, FOK, and other
  expiry behaviors plus broker defaults.[4][5]
- **SymbolProperties database** - provides tick size, lot size, contract multipliers,
  and native currency for order rounding and validation.[6]

### B. Market Hours and Calendars

- **SecurityExchangeHours / MarketHoursDatabase** - models regular, pre, and post
  sessions, plus early close and holiday calendars used to gate order submission
  windows.[7]

### C. Buying Power and Leverage

- **IBuyingPowerModel** - computes margin availability, uses broker or product
  specific leverage thresholds, and returns the maximum allowable quantity prior
  to order acceptance.[8][9]

### D. Fill Quality and Slippage

- **Fill models** - determine execution price and quantity per order type (market,
  limit, stop, auction open/close).[10]
- **Slippage models** - apply spread, volume share, or impact driven adjustments
  to simulated fills with extensible presets.[11]

### E. Fees, Settlement, and Cashflow

- **Fee models (IFeeModel)** - inject broker or venue specific commission
  schedules (flat, tiered, percentage) into execution events.[12]
- **Settlement models** - manage T+N cash movements and enforce settlement delays
  for each asset class.[13][24]
- **Margin interest rate models** - accrue borrowing costs across time with
  configurable rate tables.[14][15][16][17]
- **CashBook** - tracks multi currency balances and foreign exchange impacts on
  equity.[16][17]

### F. Short Availability

- **IShortableProvider** - supplies per symbol borrow availability and costs; lack
  of inventory blocks short sales.[18][19]

### G. Live Brokerage Connectivity

- **IBrokerage** implementations - provide order routing, status updates, and
  market data wiring for live deployment once the simulation layer is correct.[20][21]

---

## 3. Building a Brokerage Profile Pipeline

Lean applies its brokerage models by composing a security initializer and an
execution pipeline. Recreate the same orchestration when porting the concept.

### (0) During Security Initialization

- Apply a `BrokerageProfile` (the Lean equivalent of `SecurityInitializer`)
  containing the models and providers listed above.[1]
- Persist symbol metadata (tick size, contract multiplier, default exchange hours).

### (1) Pre Trade Validation

- Validate order size and price against symbol metadata.
- Guard against market session violations using the exchange hours provider.
- Enforce broker specific constraints (extended hours eligibility, asset coverage,
  leverage requirements) via `CanSubmitOrder` hooks.

### (2) Execution and Fill Calculation

- Run fill models to determine price and quantity.
- Apply slippage policies and clamp to available volume if partials are allowed.
- Attach fee model output to the execution record.

### (3) Post Trade Accounting

- Update cash balances through the settlement model.
- Accrue or rebate margin interest.
- Record borrow usage when short inventory is consumed.

---

## 4. Brokerage Profile Design Checklist

Use this checklist while drafting a profile:

1. Symbol and exchange providers - verify orders obey tick size, lot size, and
   open hours.[6][7]
2. Buying power model - unit test maximum quantity calculations and idle margin
   ratios.[8][9]
3. Fill, slippage, and fee models - confirm execution events include the correct
   adjustments.[10][11][12]
4. Settlement and interest - simulate time based cashflows and accruals.[13][14][15]
5. Shortable provider - regression test short rejection and approval scenarios.[18]
6. Integrated pipeline - run end to end cases covering regular and extended hours,
   IOC/FOK expirations, tick size violations, and oversized orders.
7. Broker specific restrictions - encode one off limitations (unsupported assets,
   market hours gaps) inside validation hooks.[23]
8. Live connectivity (optional) - ensure an `IBrokerage` adapter shares the same
   models so simulated and live behavior stay aligned.[20][21]

---

## 5. Recommended QMTL Module Placement

Goal: inject a broker profile without violating DAG purity.

1. **BrokerageProfile (global configuration)**  
   Contains `{ FillModel, SlippageModel, FeeModel, BuyingPowerModel, SettlementModel,
   ShortableProvider, MarginInterestModel, ExchangeHoursProvider, SymbolPropertiesProvider,
   OrderProperties }`. The profile plays the `SecurityInitializer` role when a
   strategy registers instruments.[1]
2. **ExecutionNode (DAG node)**  
   Inputs: orders, market data, brokerage profile. Performs pre trade validation,
   fill computation, slippage, and fees before emitting execution events. Supports
   IOC/FOK and volume limit behavior.
3. **Portfolio and CashBook service**  
   Applies settlement schedules and margin interest on a timed basis, updating the
   multi currency CashBook.[16]
4. **ShortableProvider service/cache**  
   Supplies borrow availability per symbol and trading day; rejects shorts when
  inventory is exhausted.[18]
5. **ExchangeHours and calendar provider**  
   Controls order windows and handles holiday schedules.[7]

---

## 6. Example: IBKR Profile Recipe

Use the following Lean components to approximate an Interactive Brokers profile:

- Buying power: margin/cash account models with idle percentage thresholds.[8][2]
- Fill: equity and futures fill models supporting auction open/close pricing.[10]
- Slippage: volume share or spread presets.[11]
- Fees: Interactive Brokers commission model (tiers, minimums).[12]
- Settlement: equity T+2/T+1 schedules.[24]
- Short availability: US short availability dataset or equivalent provider.[25]
- Exchange hours and restrictions: IBKR validation inside `CanExecuteOrder`.[23]

---

## 7. POC Implementation Checklist

1. Symbol and hours provider - test tick size and calendar validation.[6]
2. Buying power model - confirm maximum order quantities and margin ratios.[9]
3. Fill, slippage, fee pipeline - inspect execution events for adjustments.[10][11][12]
4. Settlement and margin interest - time shift cashflow simulation.[13][14]
5. Shortable provider - regression covers borrow rejection and approval.[18]
6. Integrated scenarios - run full pipeline tests across regular/extended hours,
   IOC/FOK expirations, minimum quantity failures, and large order handling.

### Wrap-up

Lean's brokerage model is effectively **a bundle of broker specific reality models
paired with pre trade validation hooks**. Package the models outlined above into a
`BrokerageProfile`, apply it through a `SecurityInitializer`, and you can replay
broker accurate fills, costs, settlement, and constraints inside QMTL. Extending
to live trading only requires pairing the same profile with an `IBrokerage`
adapter for order routing.[20][26]

---

## Integration Note: Worlds and Brokerage

- **Activation vs. execution** - WorldService decides whether a strategy/side may
  trade. Brokerage profiles execute orders once activation allows them.
- **Separation of concerns** - Gateway/SDK enforce activation via the order gate
  before brokerage logic runs. The brokerage layer never changes activation
  outcomes.
- **Safety defaults** - If activation is stale or unavailable, orders are blocked
  regardless of brokerage results.

### QMTL Module Mapping (Implementation Pointers)

- Orders and TIF: `qmtl/runtime/brokerage/order.py`
- Fill models: `qmtl/runtime/brokerage/fill_models.py`
- Slippage models: `qmtl/runtime/brokerage/slippage.py`
- Fees: `qmtl/runtime/brokerage/fees.py`
- Symbol properties: `qmtl/runtime/brokerage/symbols.py`
- Exchange hours: `qmtl/runtime/brokerage/exchange_hours.py`
- Shortable provider: `qmtl/runtime/brokerage/shortable.py`
- Profiles and initializer: `qmtl/runtime/brokerage/profile.py`
- Settlement and interest scaffolding: `qmtl/runtime/brokerage/settlement.py`,
  `qmtl/runtime/brokerage/interest.py`
- SDK order gate: `qmtl/runtime/sdk/order_gate.py`

See also `docs/reference/api/brokerage.md` for the public API surface.

[1]: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings?utm_source=chatgpt.com "Settings"
[2]: https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com "Common/Brokerages/IBrokerageModel.cs Source File"
[3]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/interactive-brokers?utm_source=chatgpt.com "Interactive Brokers"
[4]: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-properties?utm_source=chatgpt.com "Order Properties - QuantConnect.com"
[5]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Orders_1_1TimeInForce.html?utm_source=chatgpt.com "QuantConnect.Orders.TimeInForce Class Reference - LEAN"
[6]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SymbolProperties.html?utm_source=chatgpt.com "QuantConnect.Securities.SymbolProperties Class Reference"
[7]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SecurityExchangeHours.html?utm_source=chatgpt.com "QuantConnect.Securities.SecurityExchangeHours Class Reference"
[8]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source=chatgpt.com "Buying Power"
[9]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IBuyingPowerModel.html?utm_source=chatgpt.com "QuantConnect.Securities.IBuyingPowerModel Interface Reference"
[10]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com "Trade Fills"
[11]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts?utm_source=chatgpt.com "Slippage"
[12]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts?utm_source=chatgpt.com "Transaction Fees"
[13]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts?utm_source=chatgpt.com "Settlement"
[14]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/margin-interest-rate/key-concepts?utm_source=chatgpt.com "Margin Interest Rate"
[15]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IMarginInterestRateModel.html?utm_source=chatgpt.com "Lean: QuantConnect.Securities.IMarginInterestRateModel Interface Reference"
[16]: https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/cashbook?utm_source=chatgpt.com "Cashbook"
[17]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1Cash.html?utm_source=chatgpt.com "QuantConnect.Securities.Cash Class Reference"
[18]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_source=chatgpt.com "QuantConnect.Interfaces.IShortableProvider Interface Reference"
[19]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/short-availability/key-concepts?utm_source=chatgpt.com "Short Availability"
[20]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IBrokerage.html?utm_source=chatgpt.com "QuantConnect.Interfaces.IBrokerage Interface Reference"
[21]: https://www.quantconnect.com/docs/v2/lean-engine/contributions/brokerages/laying-the-foundation?utm_source=chatgpt.com "Laying the Foundation"
[22]: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours?utm_source=chatgpt.com "Market Hours"
[23]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Brokerages_1_1InteractiveBrokersBrokerageModel.html?utm_source=chatgpt.com "Lean: QuantConnect.Brokerages.InteractiveBrokersBrokerageModel Class Reference"
[24]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/supported-models?utm_source=chatgpt.com "Supported Settlement Models"
[25]: https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equities-short-availability?utm_source=chatgpt.com "US Equities Short Availability"
[26]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts?utm_source=chatgpt.com "Reality Modeling Overview"

{{ nav_links() }}
