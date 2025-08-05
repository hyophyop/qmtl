"""Indicator node processors."""

__all__ = ["sample_indicator"]


def sample_indicator(data: dict) -> int | float:
    """Double the ``value`` entry of the input mapping.

    Parameters
    ----------
    data:
        Mapping that may include a ``"value"`` key with a numeric value.

    Returns
    -------
    int | float
        Twice the numeric ``value`` if provided, otherwise ``0``.
    """

    return data.get("value", 0) * 2
