"""Shared runtime flags for SDK features."""

import os

# Global flag to disable Ray usage across SDK components.
NO_RAY: bool = False

# Enable conservative time budgets in tests to avoid hangs.
# Set QMTL_TEST_MODE=1 (or true/yes/on) to activate.
TEST_MODE: bool = str(os.getenv("QMTL_TEST_MODE", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# When set, override wall-clock 'now' used by history warm-up.
_fixed_now = os.getenv("QMTL_FIXED_NOW", "").strip()
try:
    FIXED_NOW: int | None = int(_fixed_now) if _fixed_now else None
except ValueError:
    FIXED_NOW = None

# Default client-side timeouts used by SDK components. These are intentionally
# small under TEST_MODE to surface issues quickly and prevent hangs.
HTTP_TIMEOUT_SECONDS: float = 1.5 if TEST_MODE else 2.0
WS_RECV_TIMEOUT_SECONDS: float = 5.0 if TEST_MODE else 30.0
WS_MAX_TOTAL_TIME_SECONDS: float | None = 5.0 if TEST_MODE else None

# Strict gap handling (opt-in). When enabled, Runner will raise if
# pre_warmup remains after history reconciliation.
FAIL_ON_HISTORY_GAP: bool = str(os.getenv("QMTL_FAIL_ON_HISTORY_GAP", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Default poll interval for explicit status queries (seconds).
POLL_INTERVAL_SECONDS: float = 2.0 if TEST_MODE else 10.0
