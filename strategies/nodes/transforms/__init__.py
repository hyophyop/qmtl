"""Transform node processors."""

from .publisher import publisher_node

__all__ = ["sample_transform", "publisher_node"]


def sample_transform(value: int) -> int:
    """Modify the indicator value before output."""
    return value - 1
