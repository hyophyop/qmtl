from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class HubMetrics:
    """Callback bundle used by :class:`WebSocketHub` instrumentation."""

    record_event_dropped: Callable[[str], None]
    record_event_fanout: Callable[[str, int], None]
    update_ws_subscribers: Callable[[dict[str, int]], None]
    record_ws_drop: Callable[[int], None]

    @classmethod
    def default(cls) -> "HubMetrics":
        """Return metrics callbacks backed by :mod:`qmtl.services.gateway.metrics`."""

        from .. import metrics as gateway_metrics

        return cls(
            record_event_dropped=gateway_metrics.record_event_dropped,
            record_event_fanout=gateway_metrics.record_event_fanout,
            update_ws_subscribers=gateway_metrics.update_ws_subscribers,
            record_ws_drop=gateway_metrics.record_ws_drop,
        )


NOOP_METRICS = HubMetrics(
    record_event_dropped=lambda _topic: None,
    record_event_fanout=lambda _topic, _recipients: None,
    update_ws_subscribers=lambda _counts: None,
    record_ws_drop=lambda _count: None,
)
