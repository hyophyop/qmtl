"""Generator node processors."""

from .sequence import sequence_generator_node


def sample_generator():
    """Generate sample data for downstream nodes."""
    return {"value": 42}


__all__ = ["sequence_generator_node", "sample_generator"]
