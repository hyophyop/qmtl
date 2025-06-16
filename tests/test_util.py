import pytest
from qmtl.sdk.util import parse_interval, parse_period


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
    with pytest.raises(ValueError):
        parse_interval("bad")


@pytest.mark.parametrize(
    "value,expected",
    [
        (10, 10),
        ("30m", 1800),
    ],
)
def test_parse_period(value, expected):
    assert parse_period(value) == expected
