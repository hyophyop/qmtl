from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def format_event(
    source: str,
    event_type: str,
    data: dict[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Return a CloudEvents-formatted dictionary.

    ``correlation_id`` allows callers to associate related events across
    services. When omitted a new random identifier is generated.
    """

    return {
        "specversion": "1.0",
        "id": str(uuid4()),
        "source": source,
        "type": event_type,
        "time": datetime.now(tz=timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": data,
        "correlation_id": correlation_id or str(uuid4()),
    }

__all__ = ["format_event"]
