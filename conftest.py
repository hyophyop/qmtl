"""Top-level pytest configuration.

Expose optional fixture plugins globally to satisfy pytest's requirement that
``pytest_plugins`` be declared in a top-level conftest when it should affect
the entire suite.
"""

import asyncio

import pytest

pytest_plugins = (
    "tests.e2e.world_smoke.fixtures_inprocess",
    "tests.e2e.world_smoke.fixtures_docker",
)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    """Ensure async-marked tests always have a current main-thread event loop."""

    if pyfuncitem.get_closest_marker("asyncio") is not None:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
    yield
