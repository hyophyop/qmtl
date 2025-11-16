import pytest

from qmtl.runtime.sdk._message_registry import AsyncMessageRegistry
from qmtl.runtime.sdk._normalizers import (
    extract_message_payload,
    normalize_interval,
    normalize_tags,
)


@pytest.mark.asyncio
async def test_dispatch_invokes_registered_handler():
    registry = AsyncMessageRegistry()
    received: dict[str, object] = {}

    async def handler(payload: dict[str, object]) -> None:
        received.update(payload)

    registry.register("evt", handler)

    dispatched = await registry.dispatch("evt", {"value": "ok"})

    assert dispatched is True
    assert received == {"value": "ok"}


@pytest.mark.asyncio
async def test_dispatch_ignores_unknown_event():
    registry = AsyncMessageRegistry()

    dispatched = await registry.dispatch("missing", {"value": 1})

    assert dispatched is False


@pytest.mark.parametrize(
    "message, expected",
    [
        ({"event": "foo", "data": {"version": 2}}, None),
        ("not-a-dict", None),
        ({"event": "foo", "data": {"version": 1, "value": "x"}}, ("foo", {"version": 1, "value": "x"})),
        ({"type": "foo", "version": 1, "payload": 1}, ("foo", {"type": "foo", "version": 1, "payload": 1})),
    ],
)
def test_extract_message_payload(message, expected):
    assert extract_message_payload(message) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [(["a", "b"], ("a", "b")), (" a , b ", ("a", "b")), (None, tuple())],
)
def test_normalize_tags(raw, expected):
    assert normalize_tags(raw) == expected


@pytest.mark.parametrize("raw, expected", [("10", 10), (None, None), ("bad", None)])
def test_normalize_interval(raw, expected):
    assert normalize_interval(raw) == expected
