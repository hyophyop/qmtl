#!/usr/bin/env python3
"""Seamless runtime health verification CLI.

This script validates that required environment variables are populated,
confirms the distributed coordinator is reachable, and ensures that
Prometheus exposes the expected metrics.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import httpx

DEFAULT_REQUIRED_ENV = ("QMTL_SEAMLESS_COORDINATOR_URL",)
DEFAULT_PROMETHEUS_METRICS = (
    "backfill_completion_ratio",
    "seamless_sla_deadline_seconds",
)
DEFAULT_COORDINATOR_HEALTH_PATH = "/health"

HttpGet = Callable[[str, dict[str, str] | None, float], httpx.Response]


@dataclass
class CheckResult:
    """Outcome of a health check."""

    name: str
    success: bool
    message: str

    def format(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.name}: {self.message}"


def _http_get(url: str, params: dict[str, str] | None, timeout: float) -> httpx.Response:
    return httpx.get(url, params=params, timeout=timeout)


def verify_required_env(
    env_names: Sequence[str],
    *,
    environ: dict[str, str] | None = None,
) -> CheckResult:
    env = environ if environ is not None else os.environ
    missing = [name for name in env_names if not env.get(name)]
    if missing:
        return CheckResult(
            name="Environment variables",
            success=False,
            message=f"Missing values for: {', '.join(sorted(missing))}",
        )
    return CheckResult(
        name="Environment variables",
        success=True,
        message=f"All {len(env_names)} required environment variables are set",
    )


def check_coordinator_health(
    base_url: str | None,
    *,
    path: str = DEFAULT_COORDINATOR_HEALTH_PATH,
    timeout: float = 5.0,
    http_get: HttpGet | None = None,
) -> CheckResult:
    if not base_url:
        return CheckResult(
            name="Coordinator health",
            success=False,
            message="Coordinator URL not provided",
        )

    url = f"{base_url.rstrip('/')}{path}"
    getter = http_get or _http_get
    try:
        response = getter(url, None, timeout)
    except httpx.RequestError as exc:
        return CheckResult(
            name="Coordinator health",
            success=False,
            message=f"Request failed: {exc}",
        )

    if response.status_code >= 400:
        return CheckResult(
            name="Coordinator health",
            success=False,
            message=f"Received HTTP {response.status_code} from {url}",
        )

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        status = payload.get("status") or payload.get("state")
        if status and str(status).lower() not in {"ok", "healthy", "pass"}:
            return CheckResult(
                name="Coordinator health",
                success=False,
                message=f"Coordinator reported unhealthy status: {status}",
            )

    return CheckResult(
        name="Coordinator health",
        success=True,
        message=f"Coordinator at {url} responded with HTTP {response.status_code}",
    )


def check_prometheus_metrics(
    base_url: str | None,
    metrics: Iterable[str],
    *,
    timeout: float = 5.0,
    http_get: HttpGet | None = None,
) -> CheckResult:
    metric_list = [metric for metric in metrics if metric]
    if not metric_list:
        return CheckResult(
            name="Prometheus metrics",
            success=True,
            message="No Prometheus metrics requested; skipping",
        )

    if not base_url:
        return CheckResult(
            name="Prometheus metrics",
            success=False,
            message="Prometheus URL not provided",
        )

    getter = http_get or _http_get
    missing: list[str] = []
    for metric in metric_list:
        params = {"match[]": metric}
        url = f"{base_url.rstrip('/')}/api/v1/series"
        try:
            response = getter(url, params, timeout)
        except httpx.RequestError as exc:
            return CheckResult(
                name="Prometheus metrics",
                success=False,
                message=f"Request failed for metric '{metric}': {exc}",
            )

        if response.status_code >= 400:
            return CheckResult(
                name="Prometheus metrics",
                success=False,
                message=f"HTTP {response.status_code} querying '{metric}'",
            )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if not isinstance(payload, dict) or payload.get("status") != "success":
            return CheckResult(
                name="Prometheus metrics",
                success=False,
                message=f"Unexpected response for metric '{metric}'",
            )

        series = payload.get("data")
        if not series:
            missing.append(metric)

    if missing:
        return CheckResult(
            name="Prometheus metrics",
            success=False,
            message="Missing series for: " + ", ".join(sorted(missing)),
        )

    return CheckResult(
        name="Prometheus metrics",
        success=True,
        message=f"All {len(metric_list)} metrics returned active series",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required-env",
        action="append",
        dest="required_env",
        help="Environment variable that must be populated (can be passed multiple times)",
    )
    parser.add_argument(
        "--coordinator-url",
        default=os.getenv("QMTL_SEAMLESS_COORDINATOR_URL", ""),
        help="Distributed coordinator base URL (default: QMTL_SEAMLESS_COORDINATOR_URL)",
    )
    parser.add_argument(
        "--coordinator-health-path",
        default=DEFAULT_COORDINATOR_HEALTH_PATH,
        help="Path appended to the coordinator URL for the health probe (default: /health)",
    )
    parser.add_argument(
        "--prometheus-url",
        default=os.getenv("QMTL_PROMETHEUS_URL") or os.getenv("PROMETHEUS_URL", ""),
        help="Prometheus base URL (default: QMTL_PROMETHEUS_URL or PROMETHEUS_URL)",
    )
    parser.add_argument(
        "--prometheus-metric",
        action="append",
        dest="prometheus_metrics",
        help="Prometheus metric to verify (can be passed multiple times)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout for coordinator and Prometheus requests (seconds)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    required_env = tuple(args.required_env) if args.required_env else DEFAULT_REQUIRED_ENV
    prometheus_metrics = (
        tuple(args.prometheus_metrics)
        if args.prometheus_metrics
        else DEFAULT_PROMETHEUS_METRICS
    )

    results = [
        verify_required_env(required_env),
        check_coordinator_health(
            args.coordinator_url,
            path=args.coordinator_health_path,
            timeout=args.timeout,
        ),
        check_prometheus_metrics(
            args.prometheus_url,
            prometheus_metrics,
            timeout=args.timeout,
        ),
    ]

    for result in results:
        print(result.format())

    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
