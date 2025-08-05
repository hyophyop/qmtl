import pytest

from strategies.nodes.indicators import sample_indicator


def test_sample_indicator_returns_double_value():
    assert sample_indicator({"value": 10}) == 20


def test_sample_indicator_defaults_to_zero():
    assert sample_indicator({}) == 0
