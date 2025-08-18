"""Numeric sequence generator node."""

# Source: docs/alphadocs/basic_sequence_pipeline.md

TAGS = {
    "scope": "generator",
    "family": "sequence",
    "interval": "1d",
    "asset": "sample",
}


def sequence_generator_node():
    """Generate a simple numeric sequence."""
    return {"numbers": [1, 2, 3]}
