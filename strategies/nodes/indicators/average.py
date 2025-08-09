"""Compute the average of a numeric sequence."""

# Source: docs/alphadocs/basic_sequence_pipeline.md


def average_indicator_node(data):
    """Return the average of numbers produced by the generator."""
    numbers = data.get("numbers", [])
    return {"average": sum(numbers) / len(numbers)}
