from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


EVENT_SCHEMA_VERSION = 1


def format_event(
    source: str, event_type: str, data: dict[str, Any], *, correlation_id: str | None = None
) -> dict[str, Any]:
    """Return a CloudEvents-formatted dictionary with ``correlation_id``."""

    if correlation_id is None:
        correlation_id = str(uuid4())
    return {
        "specversion": "1.0",
        "id": str(uuid4()),
        "source": source,
        "type": event_type,
        "time": datetime.now(tz=timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": data,
        "correlation_id": correlation_id,
    }

__all__ = ["format_event", "EVENT_SCHEMA_VERSION"]
