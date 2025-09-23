import pytest
from qmtl.runtime.sdk.util import parse_interval, parse_period
from qmtl.runtime.sdk.exceptions import InvalidIntervalError, InvalidPeriodError


@pytest.mark.parametrize(
    "value,expected",
    [
        (60, 60),
        ("45s", 45),
        ("30m", 1800),
        ("1h", 3600),
    ],
)
def test_parse_interval(value, expected):
    assert parse_interval(value) == expected


def test_parse_interval_invalid():
    with pytest.raises(InvalidIntervalError):
        parse_interval("bad")


@pytest.mark.parametrize(
    "value,expected",
    [
        (10, 10),
    ],
)
def test_parse_period(value, expected):
    assert parse_period(value) == expected

def test_parse_period_invalid():
    with pytest.raises(InvalidPeriodError):
        parse_period("30m")
