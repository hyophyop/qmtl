from __future__ import annotations

from asyncio import CancelledError
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Protocol, TypeVar

TCommandResponse = TypeVar("TCommandResponse", covariant=True)
TParseInput = TypeVar("TParseInput", contravariant=True)
TResult = TypeVar("TResult", covariant=True)


class RpcCommand(Protocol[TCommandResponse]):
    """Command abstraction for a single RPC invocation.

    Implementations encapsulate request construction and the low-level
    transport call (HTTP/gRPC/etc.) and return a transport-level response.
    """

    async def execute(self) -> TCommandResponse:
        """Execute the underlying RPC and return a response."""


class RpcResponseParser(Protocol[TParseInput, TResult]):
    """Parser that converts transport responses into domain results."""

    def parse(self, response: TParseInput) -> TResult:
        """Normalize and validate the transport response."""


@dataclass(slots=True)
class RpcError:
    """Structured error information for RPC commands."""

    message: str
    cause: Exception | None = None
    details: dict[str, Any] | None = None


@dataclass(slots=True)
class RpcOutcome(Generic[TResult]):
    """Outcome of an RPC invocation with optional error metadata."""

    result: TResult | None = None
    error: RpcError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


async def execute_rpc(
    command: RpcCommand[TCommandResponse],
    parser: RpcResponseParser[TCommandResponse, TResult],
    *,
    on_error: Callable[[Exception], RpcError] | None = None,
) -> RpcOutcome[TResult]:
    """Execute an RPC command and parse the response into a domain outcome.

    This helper is intentionally small: it centralizes the \"command + parser\"
    handshake while leaving retry/circuit-breaker/metrics concerns to the
    surrounding adapter layer.
    """

    try:
        response = await command.execute()
        return RpcOutcome(result=parser.parse(response))
    except CancelledError:
        raise
    except Exception as exc:  # pragma: no cover - specifics validated by callers
        if on_error is not None:
            error = on_error(exc)
        else:
            error = RpcError(message=str(exc), cause=exc)
        return RpcOutcome(error=error)

