from __future__ import annotations

"""Utilities for One-Cancels-Other (OCO) order pairs using live connectors."""

from dataclasses import dataclass
from typing import Any, Tuple

from .brokerage_client import BrokerageClient


@dataclass
class OCOOrder:
    """Represent an OCO order pair for live brokerage clients.

    The two legs are submitted sequentially. If either leg immediately
    completes, the opposite leg is canceled. The helper returns broker
    responses for both legs after any cancellation handling.
    """

    first: dict[str, Any]
    second: dict[str, Any]

    def execute(self, client: BrokerageClient) -> Tuple[dict[str, Any], dict[str, Any]]:
        """Submit both legs and enforce cancel-on-fill semantics."""

        resp_first = client.post_order(self.first)
        resp_second = client.post_order(self.second)

        def _done(resp: dict[str, Any] | None) -> bool:
            return bool(resp) and resp.get("status") in {"completed", "filled"}

        # If the first leg filled, cancel the second.
        if _done(resp_first):
            oid = resp_second.get("id")
            if oid is not None:
                client.cancel_order(str(oid))
                # refresh status after cancel
                refreshed = client.poll_order_status({"id": oid})
                if isinstance(refreshed, dict):
                    resp_second = refreshed
        # Otherwise if the second leg filled first, cancel the first.
        elif _done(resp_second):
            oid = resp_first.get("id")
            if oid is not None:
                client.cancel_order(str(oid))
                refreshed = client.poll_order_status({"id": oid})
                if isinstance(refreshed, dict):
                    resp_first = refreshed

        return resp_first, resp_second
