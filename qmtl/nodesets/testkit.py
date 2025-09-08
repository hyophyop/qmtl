from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from qmtl.sdk.node import Node
from .base import NodeSetBuilder, NodeSet


def attach_minimal(builder: NodeSetBuilder, signal: Node, world_id: str) -> NodeSet:
    """Attach the node set behind ``signal`` using default options.

    Returns the composed :class:`NodeSet` for testing.
    """
    return builder.attach(signal, world_id=world_id)


def make_cloudevent(event_type: str, source: str, data: dict) -> dict:
    """Make a minimal CloudEvents 1.0 JSON object for tests."""
    return {
        "specversion": "1.0",
        "id": str(uuid.uuid4()),
        "source": source,
        "type": event_type,
        "time": datetime.now(timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": data,
    }


def fake_fill_webhook(symbol: str, quantity: float, price: float, **extra) -> dict:
    """Create a fake fill CloudEvent for webhook simulation in tests."""
    payload = {"symbol": symbol, "quantity": float(quantity), "fill_price": float(price)}
    payload.update(extra)
    return make_cloudevent("trade.fill", "qmtl.testkit", payload)


__all__ = ["attach_minimal", "make_cloudevent", "fake_fill_webhook"]

