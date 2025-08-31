---
title: "Brokerage API"
tags: [api]
author: "QMTL Team"
last_modified: 2025-08-31
---

{{ nav_links() }}

# Brokerage API

- qmtl.brokerage interfaces: BuyingPowerModel, FillModel, SlippageModel, FeeModel
- Fill models: MarketFillModel, LimitFillModel, StopMarketFillModel, StopLimitFillModel
- Slippage models: NullSlippageModel, ConstantSlippageModel, SpreadBasedSlippageModel, VolumeShareSlippageModel
- Fee models: PerShareFeeModel, PercentFeeModel, CompositeFeeModel
- Providers: SymbolPropertiesProvider (tick/lot/min), ExchangeHoursProvider (regular/pre/post), ShortableProvider
- Profiles: BrokerageProfile, SecurityInitializer, ibkr_equities_like_profile()

Usage skeleton:

```python
from qmtl.brokerage import (
    BrokerageModel, CashBuyingPowerModel,
    MarketFillModel, PerShareFeeModel,
    NullSlippageModel, SymbolPropertiesProvider,
)

model = BrokerageModel(
    CashBuyingPowerModel(),
    PerShareFeeModel(),
    NullSlippageModel(),
    MarketFillModel(),
    symbols=SymbolPropertiesProvider(),
)
```

{{ nav_links() }}

