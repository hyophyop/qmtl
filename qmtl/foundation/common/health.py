"""Standardized HTTP health probing utilities.

This module exposes a reusable :class:`CheckResult` data structure and helper
functions that classify HTTP responses and transport errors into a fixed set of
result codes.  It also instruments each probe with Prometheus metrics so callers
receive consistent observability across services.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import socket
import time
from collections.abc import Mapping
from typing import Any, Callable, Iterable, Literal, MutableMapping

import httpx
from prometheus_client import CollectorRegistry, REGISTRY as global_registry

from .metrics_factory import (
    get_or_create_counter,
    get_or_create_gauge,
    get_or_create_histogram,
)

__all__ = [
    "CheckResult",
    "Code",
    "classify_result",
    "probe_http",
    "probe_http_async",
]

Code = Literal["OK", "CLIENT_ERROR", "SERVER_ERROR", "TIMEOUT", "NETWORK", "UNKNOWN"]


@dataclass(slots=True)
class CheckResult:
    """Outcome of a health probe.

    Attributes
    ----------
    ok:
        ``True`` when the probe was successful (HTTP 2xx).
    code:
        Normalised classification code for the probe result.
    status:
        Raw HTTP status code when a response was received, otherwise ``None``.
    err:
        Textual description of the failure when an exception occurred.
    latency_ms:
        Wall-clock latency measured in milliseconds.
    """

    ok: bool
    code: Code
    status: int | None = None
    err: str | None = None
    latency_ms: float | None = None


_TIMEOUT_EXC = (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError, socket.timeout)
_NETWORK_EXC = (httpx.NetworkError, ConnectionError, OSError)


def classify_result(status: int | None, error: BaseException | None = None) -> Code:
    """Classify a probe outcome into a :class:`Code` value.

    Parameters
    ----------
    status:
        HTTP status code when available.
    error:
        Exception raised during the probe, if any.
    """

    if error is not None:
        if isinstance(error, _TIMEOUT_EXC):
            return "TIMEOUT"
        if isinstance(error, _NETWORK_EXC):
            return "NETWORK"
        return "UNKNOWN"

    if status is None:
        return "UNKNOWN"
    if 200 <= status < 300:
        return "OK"
    if 400 <= status < 500:
        return "CLIENT_ERROR"
    if 500 <= status < 600:
        return "SERVER_ERROR"
    return "UNKNOWN"


def _record_metrics(
    result: CheckResult,
    *,
    service: str,
    endpoint: str,
    method: str,
    latency_seconds: float,
    registry: CollectorRegistry | None,
) -> None:
    reg = registry or global_registry
    counter = get_or_create_counter(
        "probe_requests_total",
        "Total number of HTTP health probes",
        ["service", "endpoint", "method", "result"],
        registry=reg,
        test_value_attr="_value",
        test_value_factory=lambda: 0.0,
    )
    histogram = get_or_create_histogram(
        "probe_latency_seconds",
        "Latency distribution for HTTP health probes",
        ["service", "endpoint", "method"],
        registry=reg,
        test_value_attr="_sum",
        test_value_factory=lambda: 0.0,
    )
    gauge = get_or_create_gauge(
        "probe_last_ok_timestamp",
        "Unix timestamp of the most recent successful probe",
        ["service", "endpoint"],
        registry=reg,
        test_value_attr="_value",
        test_value_factory=lambda: 0.0,
    )

    counter.labels(service=service, endpoint=endpoint, method=method, result=result.code).inc()
    histogram.labels(service=service, endpoint=endpoint, method=method).observe(latency_seconds)
    if result.ok:
        gauge.labels(service=service, endpoint=endpoint).set(time.time())


def _finalise_result(
    *,
    status: int | None,
    error: BaseException | None,
    error_message: str | None,
    latency_seconds: float,
    service: str,
    endpoint: str,
    method: str,
    registry: CollectorRegistry | None,
) -> CheckResult:
    code = classify_result(status, error)
    result = CheckResult(
        ok=(code == "OK"),
        code=code,
        status=status,
        err=error_message,
        latency_ms=latency_seconds * 1000.0,
    )
    _record_metrics(
        result,
        service=service,
        endpoint=endpoint,
        method=method,
        latency_seconds=latency_seconds,
        registry=registry,
    )
    return result


RequestCallable = Callable[..., httpx.Response]


def _prepare_request_kwargs(**kwargs: Any) -> MutableMapping[str, Any]:
    allowed: Iterable[str] = (
        "timeout",
        "headers",
        "params",
        "content",
        "data",
        "json",
        "auth",
    )
    prepared: MutableMapping[str, Any] = {}
    for key in allowed:
        if key in kwargs and kwargs[key] is not None:
            prepared[key] = kwargs[key]
    return prepared


def probe_http(
    url: str,
    *,
    method: str = "GET",
    service: str,
    endpoint: str,
    timeout: float | httpx.Timeout | None = 3.0,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    data: Any = None,
    json: Any = None,
    auth: Any = None,
    client: httpx.Client | None = None,
    request: RequestCallable | None = None,
    metrics_registry: CollectorRegistry | None = None,
) -> CheckResult:
    """Perform a synchronous HTTP probe and classify the outcome."""

    prepared_kwargs = _prepare_request_kwargs(
        timeout=timeout,
        headers=headers,
        params=params,
        data=data,
        json=json,
        auth=auth,
    )

    status: int | None = None
    err_msg: str | None = None
    caught: BaseException | None = None
    start = time.perf_counter()
    method_upper = method.upper()
    try:
        if request is not None:
            response = request(method_upper, url, **prepared_kwargs)
        elif client is not None:
            response = client.request(method_upper, url, **prepared_kwargs)
        else:
            response = httpx.request(method_upper, url, **prepared_kwargs)
        status = response.status_code
    except BaseException as exc:  # noqa: BLE001 - we classify below
        caught = exc
        err_msg = str(exc)
    latency_seconds = time.perf_counter() - start
    return _finalise_result(
        status=status,
        error=caught,
        error_message=err_msg,
        latency_seconds=latency_seconds,
        service=service,
        endpoint=endpoint,
        method=method_upper,
        registry=metrics_registry,
    )


async def probe_http_async(
    url: str,
    *,
    method: str = "GET",
    service: str,
    endpoint: str,
    timeout: float | httpx.Timeout | None = 3.0,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    data: Any = None,
    json: Any = None,
    auth: Any = None,
    client: httpx.AsyncClient | None = None,
    request: Callable[..., Any] | None = None,
    metrics_registry: CollectorRegistry | None = None,
) -> CheckResult:
    """Perform an asynchronous HTTP probe and classify the outcome."""

    prepared_kwargs = _prepare_request_kwargs(
        timeout=timeout,
        headers=headers,
        params=params,
        data=data,
        json=json,
        auth=auth,
    )

    status: int | None = None
    err_msg: str | None = None
    caught: BaseException | None = None
    start = time.perf_counter()
    method_upper = method.upper()
    try:
        if request is not None:
            maybe_response = request(method_upper, url, **prepared_kwargs)
            response = await maybe_response  # type: ignore[assignment]
        elif client is not None:
            response = await client.request(method_upper, url, **prepared_kwargs)
        else:
            async with httpx.AsyncClient() as local_client:
                response = await local_client.request(method_upper, url, **prepared_kwargs)
        status = response.status_code
    except BaseException as exc:  # noqa: BLE001 - we classify below
        caught = exc
        err_msg = str(exc)
    latency_seconds = time.perf_counter() - start
    return _finalise_result(
        status=status,
        error=caught,
        error_message=err_msg,
        latency_seconds=latency_seconds,
        service=service,
        endpoint=endpoint,
        method=method_upper,
        registry=metrics_registry,
    )
