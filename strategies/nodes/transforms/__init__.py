"""Transform node processors."""

__all__ = ["sample_transform"]


def sample_transform(value: int) -> int:
    """Modify the indicator value before output."""
    return value - 1
