"""Test configuration.

Filters noisy ResourceWarnings from unclosed sockets/event loops that can be
emitted by http client stubs under xdist. This keeps CI output clean without
affecting test behavior.
"""

import warnings
import asyncio
from typing import List
import pytest

warnings.filterwarnings("ignore", message="unclosed.*", category=ResourceWarning)
warnings.filterwarnings("ignore", message=".*unclosed event loop.*", category=ResourceWarning)
warnings.filterwarnings("ignore", message="unclosed <socket.*", category=ResourceWarning)


# Ensure event loops opened during tests are explicitly closed to avoid
# interpreter-level ResourceWarning spam when workers exit.
def _close_loops(loops: List[asyncio.AbstractEventLoop]) -> None:
    for loop in loops:
        if loop.is_closed():
            continue
        try:
            loop.close()
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def _track_and_close_event_loops():
    created: List[asyncio.AbstractEventLoop] = []
    orig_new_loop = asyncio.new_event_loop

    def tracking_new_loop():
        loop = orig_new_loop()
        created.append(loop)
        return loop

    asyncio.new_event_loop = tracking_new_loop
    try:
        yield
    finally:
        asyncio.new_event_loop = orig_new_loop
        # Close any default loop created by libraries
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            created.append(loop)
        except Exception:
            pass
        _close_loops(created)
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass
