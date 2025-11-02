---
title: "거래소 캘린더"
tags: [timing]
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# 거래소 캘린더

이 가이드는 주요 거래소의 예시 거래 시간을 정리하고, 점심 휴식과 조기 마감을 포함해 `MarketHours` 를 구성하는 방법을 보여줍니다.

| 거래소 | 프리마켓 | 정규장 | 점심 휴장 | 포스트마켓 | 타임존 |
|--------|----------|--------|-----------|-------------|--------|
| NYSE/NASDAQ | 04:00 | 09:30–16:00 | — | 16:00–20:00 | US/Eastern |
| CME | — | 09:30–16:00 | — | 16:00–16:15 | US/Central |
| JPX | — | 09:00–11:30 / 12:30–15:00 | 11:30–12:30 | — | Asia/Tokyo |
| KRX | — | 09:00–11:30 / 12:30–15:30 | 11:30–12:30 | — | Asia/Seoul |

```python
from datetime import date, time
from qmtl.runtime.sdk.timing_controls import MarketHours

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

`lunch_start` 와 `lunch_end` 를 사용해 중간 휴장을 표시하세요. `early_closes` 는 날짜별 조기 `regular_end` 시간을 매핑합니다.

{{ nav_links() }}
