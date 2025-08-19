"""Publish trade signals to Kafka without modifying payload."""

from __future__ import annotations

from typing import Any, Tuple


def publisher_node(signal: Any, *, topic: str) -> Tuple[str, Any]:
    """Return the given ``signal`` and ``topic`` pair.

    Parameters
    ----------
    signal:
        Message payload to publish.
    topic:
        Kafka topic name for the ``signal``.

    Returns
    -------
    tuple[str, Any]
        A ``(topic, signal)`` tuple that leaves ``signal`` untouched.
    """

    return topic, signal
