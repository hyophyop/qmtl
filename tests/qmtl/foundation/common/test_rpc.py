from __future__ import annotations

from dataclasses import dataclass

import pytest

from qmtl.foundation.common import (
    RpcCommand,
    RpcError,
    RpcOutcome,
    RpcResponseParser,
    execute_rpc,
)


@dataclass
class DummyResponse:
    payload: str


class SuccessfulCommand:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def execute(self) -> DummyResponse:
        return DummyResponse(payload=self._payload)


class EchoParser:
    def parse(self, response: DummyResponse) -> str:
        return response.payload


class FailingCommand:
    async def execute(self) -> DummyResponse:
        raise RuntimeError("rpc failed")


class UpperParser:
    def parse(self, response: DummyResponse) -> str:
        return response.payload.upper()


@pytest.mark.asyncio
async def test_execute_rpc_success() -> None:
    command: RpcCommand[DummyResponse] = SuccessfulCommand("ok")
    parser: RpcResponseParser[DummyResponse, str] = EchoParser()

    outcome: RpcOutcome[str] = await execute_rpc(command, parser)

    assert outcome.ok
    assert outcome.error is None
    assert outcome.result == "ok"


@pytest.mark.asyncio
async def test_execute_rpc_error_with_default_mapper() -> None:
    command: RpcCommand[DummyResponse] = FailingCommand()
    parser: RpcResponseParser[DummyResponse, str] = UpperParser()

    outcome = await execute_rpc(command, parser)

    assert not outcome.ok
    assert outcome.result is None
    assert isinstance(outcome.error, RpcError)
    assert "rpc failed" in outcome.error.message


@pytest.mark.asyncio
async def test_execute_rpc_error_with_custom_mapper() -> None:
    command: RpcCommand[DummyResponse] = FailingCommand()
    parser: RpcResponseParser[DummyResponse, str] = UpperParser()

    def custom_mapper(exc: Exception) -> RpcError:
        return RpcError(message="custom", cause=exc, details={"kind": "test"})

    outcome = await execute_rpc(command, parser, on_error=custom_mapper)

    assert not outcome.ok
    assert outcome.result is None
    assert isinstance(outcome.error, RpcError)
    assert outcome.error.message == "custom"
    assert outcome.error.details == {"kind": "test"}

