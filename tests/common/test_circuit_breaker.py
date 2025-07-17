import asyncio
import pytest

from qmtl.common import AsyncCircuitBreaker


@pytest.mark.asyncio
async def test_circuit_breaker_basic():
    cb = AsyncCircuitBreaker(max_failures=2, reset_timeout=0.1)
    calls = 0

    @cb
    async def flaky():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    for expected_failures in (1, 2):
        with pytest.raises(RuntimeError):
            await flaky()
        assert cb.failures == expected_failures

    assert cb.is_open
    with pytest.raises(RuntimeError):
        await flaky()
    assert cb.failures == 2

    await asyncio.sleep(0.11)
    assert not cb.is_open

    with pytest.raises(RuntimeError):
        await flaky()
    assert cb.failures == 1
    assert calls == 3


@pytest.mark.asyncio
async def test_circuit_breaker_callbacks():
    events = []
    cb = AsyncCircuitBreaker(
        max_failures=1,
        reset_timeout=0.05,
        on_open=lambda: events.append("open"),
        on_close=lambda: events.append("close"),
        on_failure=lambda count: events.append(f"fail{count}"),
    )

    @cb
    async def func():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await func()

    assert events == ["fail1", "open"]
    assert cb.is_open

    await asyncio.sleep(0.06)
    # Access property to trigger state refresh
    assert not cb.is_open
    assert events[-1] == "close"
