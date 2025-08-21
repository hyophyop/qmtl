{{ nav_links() }}

# Timing Controls

This document outlines the timing utilities available in QMTL for managing market sessions and validating timestamp data.

## MarketHours

`MarketHours` describes the boundaries of each trading session. It accepts the start and end times for pre-market, regular, and post-market sessions.

```python
from qmtl.sdk.timing_controls import MarketHours, MarketSession
from datetime import datetime, time, timezone

hours = MarketHours(
    pre_market_start=time(4, 0),
    regular_start=time(9, 30),
    regular_end=time(16, 0),
    post_market_end=time(20, 0)
)

# Wednesday 10:00 AM UTC
ts = datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc)
session = hours.get_session(ts)
assert session is MarketSession.REGULAR
```

## TimingController

`TimingController` coordinates session checks and execution delays.

- `allow_pre_post_market`: permit trading in pre/post-market sessions.
- `require_regular_hours`: only allow trading during the regular session.
- `validate_timing(timestamp)`: returns `(is_valid, reason, session)`.
- `calculate_execution_delay(...)`: estimates realistic execution delay.
- `get_next_valid_execution_time(...)`: finds the next allowable time if the current timestamp is invalid.

```python
from qmtl.sdk.timing_controls import TimingController

controller = TimingController(allow_pre_post_market=False)
valid, reason, session = controller.validate_timing(ts)
if not valid:
    print(f"Blocked {session}: {reason}")
```

## validate_backtest_timing

`validate_backtest_timing` scans all `StreamInput` nodes in a strategy and reports timestamps that fall outside the configured trading sessions. Each issue includes the timestamp, reason, and the detected market session. Set `fail_on_invalid_timing=True` to raise an exception when invalid data is found.

```python
from qmtl.sdk.timing_controls import validate_backtest_timing

issues = validate_backtest_timing(strategy)
for node, node_issues in issues.items():
    for issue in node_issues:
        print(issue["reason"], issue["datetime"])
```

{{ nav_links() }}

