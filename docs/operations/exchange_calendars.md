---
title: "Exchange Calendars"
tags: [timing]
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# Exchange Calendars

This guide lists example trading hours for several common exchanges and shows how
to configure `MarketHours` with lunch breaks and early closes.

| Exchange | Pre-Market | Regular Hours | Lunch Break | Post-Market | Timezone |
|----------|------------|---------------|-------------|-------------|----------|
| NYSE/NASDAQ | 04:00 | 09:30–16:00 | — | 16:00–20:00 | US/Eastern |
| CME | — | 09:30–16:00 | — | 16:00–16:15 | US/Central |
| JPX | — | 09:00–11:30 / 12:30–15:00 | 11:30–12:30 | — | Asia/Tokyo |
| KRX | — | 09:00–11:30 / 12:30–15:30 | 11:30–12:30 | — | Asia/Seoul |

```python
from datetime import date, time
from qmtl.sdk.timing_controls import MarketHours

hours = MarketHours(
    pre_market_start=time(4, 0),
    regular_start=time(9, 30),
    regular_end=time(16, 0),
    post_market_end=time(20, 0),
    lunch_start=time(11, 30),
    lunch_end=time(12, 30),
    early_closes={date(2024, 12, 24): time(13, 0)},
)
```

Use `lunch_start` and `lunch_end` to mark midday closures. `early_closes` maps
specific dates to early `regular_end` times.

{{ nav_links() }}


