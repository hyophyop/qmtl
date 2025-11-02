---
title: "타이밍 제어"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 타이밍 제어

이 문서는 QMTL에서 제공하는 타이밍 유틸리티를 소개합니다. 시장 세션을 관리하고 타임스탬프 데이터의 유효성을 검증하는 데 사용합니다.

## MarketHours

`MarketHours`는 각 거래 세션의 경계를 정의합니다. 프리마켓, 정규장, 애프터마켓의 시작/종료 시간을 전달받습니다.

```python
from qmtl.runtime.sdk.timing_controls import MarketHours, MarketSession
from datetime import date, datetime, time, timezone

hours = MarketHours(
    pre_market_start=time(4, 0),
    regular_start=time(9, 30),
    regular_end=time(16, 0),
    post_market_end=time(20, 0),
    lunch_start=time(11, 30),
    lunch_end=time(12, 30),
    early_closes={date(2024, 12, 24): time(13, 0)},
)

# Wednesday 10:00 AM UTC
ts = datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc)
session = hours.get_session(ts)
assert session is MarketSession.REGULAR
```

점심 시간과 특정일 조기 마감은 `lunch_start`, `lunch_end`, `early_closes` 매핑으로 설정할 수 있습니다. 주요 시장별 예시는 [거래소 캘린더](exchange_calendars.md)를 참고하세요.

## TimingController

`TimingController`는 세션 검증과 실행 지연을 조정합니다.

- `allow_pre_post_market`: 프리/애프터마켓에서의 거래 허용 여부
- `require_regular_hours`: 정규장 시간에만 거래 허용
- `validate_timing(timestamp)`: `(is_valid, reason, session)` 반환
- `calculate_execution_delay(...)`: 현실적인 실행 지연 추정
- `get_next_valid_execution_time(...)`: 현재 타임스탬프가 유효하지 않을 때 다음 허용 시각 계산

```python
from qmtl.runtime.sdk.timing_controls import TimingController

controller = TimingController(allow_pre_post_market=False)
valid, reason, session = controller.validate_timing(ts)
if not valid:
    print(f"Blocked {session}: {reason}")
```

## validate_backtest_timing

`validate_backtest_timing`은 전략의 모든 `StreamInput` 노드를 검사하여 설정된 거래 세션 범위를 벗어나는 타임스탬프를 보고합니다. 각 항목에는 타임스탬프, 사유, 감지된 시장 세션이 포함됩니다. `fail_on_invalid_timing=True`로 설정하면 유효하지 않은 데이터가 발견될 때 예외를 발생시킵니다.

```python
from qmtl.runtime.sdk.timing_controls import validate_backtest_timing

issues = validate_backtest_timing(strategy)
for node, node_issues in issues.items():
    for issue in node_issues:
        print(issue["reason"], issue["datetime"])
```

{{ nav_links() }}
