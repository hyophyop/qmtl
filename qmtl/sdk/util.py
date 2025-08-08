import re
from typing import Any

__all__ = ["parse_interval", "parse_period"]

_TIME_RE = re.compile(r"^(\d+)([smh])$")


def _parse_time_str(value: str) -> int:
    match = _TIME_RE.fullmatch(value.strip().lower())
    if not match:
        raise ValueError(f"invalid time format: {value!r}")
    num, unit = match.groups()
    sec = int(num)
    if unit == "m":
        sec *= 60
    elif unit == "h":
        sec *= 3600
    return sec


def parse_interval(value: int | str | None) -> int:
    """Parse interval strings like ``"1h"`` and return seconds."""
    if value is None:
        raise ValueError("interval must not be None")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("interval must be positive")
        return value
    if isinstance(value, str):
        return _parse_time_str(value)
    raise TypeError("interval must be int or str")


def parse_period(value: int | None) -> int:
    """Validate that ``value`` is a positive bar count and return it."""
    if value is None:
        raise ValueError("period must not be None")
    if not isinstance(value, int):
        raise TypeError("period must be int")
    if value <= 0:
        raise ValueError("period must be positive")
    return value
