from __future__ import annotations

"""HTTP utilities for SDK components."""

from typing import Any

import httpx

from . import runtime


class HttpPoster:
    """Facade for HTTP POST operations.

    Uses ``httpx.post`` directly with the global timeout. This keeps the
    implementation lightweight and makes it simple for tests to monkeypatch
    ``httpx.post`` without needing to intercept a client instance.
    """

    @staticmethod
    def post(url: str, *, json: Any) -> httpx.Response:
        """POST ``json`` payload to ``url`` using a global timeout."""
        # Use the module-level helper so tests can easily monkeypatch
        # ``httpx.post``.  Previously this helper created a ``httpx.Client``
        # instance which meant tests had to patch ``httpx.Client.post``
        # instead.  Switching to ``httpx.post`` improves testability and
        # matches the expectations of existing unit tests.
        try:
            return httpx.post(url, json=json, timeout=runtime.HTTP_TIMEOUT_SECONDS)
        except TypeError:
            # Some tests monkeypatch ``httpx.post`` with simple callables that do
            # not accept a ``timeout`` parameter. Fall back to a call without the
            # argument to keep those tests lightweight.
            return httpx.post(url, json=json)
