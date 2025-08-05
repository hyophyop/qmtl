"""Indicator node processors."""


def sample_indicator(data):
    """Derive a simple metric from the generated data."""
    return data.get("value", 0) * 2
