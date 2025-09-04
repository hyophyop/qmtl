from __future__ import annotations

"""HTTP utilities for SDK components."""

from typing import Any

import httpx

from . import runtime


class HttpPoster:
    """Facade for HTTP POST operations.

    Uses a short-lived ``httpx.Client`` configured with the global timeout
    to avoid per-call timeout arguments while keeping tests easy to patch.
    """

    @staticmethod
    def post(url: str, *, json: Any) -> httpx.Response:
        """POST ``json`` payload to ``url`` using a session-level timeout."""
        with httpx.Client(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
            return client.post(url, json=json)
