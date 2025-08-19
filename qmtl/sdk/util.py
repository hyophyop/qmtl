import re
from typing import Any

from .exceptions import InvalidIntervalError, InvalidPeriodError, InvalidTagError, InvalidNameError

__all__ = ["parse_interval", "parse_period", "validate_tag", "validate_name"]

_TIME_RE = re.compile(r"^(\d+)([smh])$")


def _parse_time_str(value: str) -> int:
    match = _TIME_RE.fullmatch(value.strip().lower())
    if not match:
        raise InvalidIntervalError(f"invalid time format: {value!r}")
    num, unit = match.groups()
    sec = int(num)
    if unit == "m":
        sec *= 60
    elif unit == "h":
        sec *= 3600
    return sec


def validate_tag(tag: str) -> str:
    """Validate that a tag is a valid string format."""
    if not isinstance(tag, str):
        raise InvalidTagError("tag must be a string")
    if not tag.strip():
        raise InvalidTagError("tag must not be empty or whitespace only")
    if len(tag) > 100:
        raise InvalidTagError("tag must not exceed 100 characters")
    # Allow alphanumeric, underscore, hyphen, and dot
    if not re.match(r'^[a-zA-Z0-9_.-]+$', tag):
        raise InvalidTagError("tag must contain only alphanumeric characters, underscore, hyphen, or dot")
    return tag.strip()


def validate_name(name: str | None) -> str | None:
    """Validate that a name is a valid string format."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise InvalidNameError("name must be a string")
    name = name.strip()
    if not name:
        raise InvalidNameError("name must not be empty or whitespace only")
    if len(name) > 200:
        raise InvalidNameError("name must not exceed 200 characters")
    return name


def parse_interval(value: int | str | None) -> int:
    """Parse interval strings like ``"1h"`` and return seconds."""
    if value is None:
        raise InvalidIntervalError("interval must not be None")
    if isinstance(value, int):
        if value <= 0:
            raise InvalidIntervalError("interval must be positive")
        if value > 86400:  # 1 day max
            raise InvalidIntervalError("interval must not exceed 24 hours (86400 seconds)")
        return value
    if isinstance(value, str):
        result = _parse_time_str(value)
        if result > 86400:  # 1 day max
            raise InvalidIntervalError("interval must not exceed 24 hours (86400 seconds)")
        return result
    raise InvalidIntervalError("interval must be int or str")


def parse_period(value: int | None) -> int:
    """Validate that ``value`` is a positive bar count and return it."""
    if value is None:
        raise InvalidPeriodError("period must not be None")
    if not isinstance(value, int):
        raise InvalidPeriodError("period must be int")
    if value <= 0:
        raise InvalidPeriodError("period must be positive")
    if value > 10000:  # reasonable upper bound
        raise InvalidPeriodError("period must not exceed 10000")
    return value
