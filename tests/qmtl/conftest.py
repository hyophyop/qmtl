"""Shared fixtures for qmtl namespace tests."""

import asyncio

import pytest


@pytest.fixture(scope="session", autouse=True)
def _provide_event_loop() -> None:
    """Ensure a default event loop exists to satisfy global teardown hooks."""

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
