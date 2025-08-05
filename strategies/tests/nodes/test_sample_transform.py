"""Tests for the sample transform."""

import pytest

from strategies.nodes.transforms import sample_transform


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (10, 9),  # typical case
        (0, -1),  # lower edge case
        (-5, -6),  # negative edge case
    ],
)
def test_sample_transform(input_value, expected):
    """sample_transform should decrement the input by one."""
    assert sample_transform(input_value) == expected
