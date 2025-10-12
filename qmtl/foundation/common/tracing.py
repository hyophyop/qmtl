from __future__ import annotations

"""OpenTelemetry tracing utilities for QMTL.

This module exposes a ``setup_tracing`` helper which configures the global
tracer provider. Traces can be exported to an OTLP compatible backend such as
Jaeger or Tempo by setting the ``QMTL_OTEL_EXPORTER_ENDPOINT`` environment
variable. When unset, spans are logged to the console which is useful for
local development.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict

from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import yaml
try:
    # Optional dependency; only needed when an OTLP endpoint is configured
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
except Exception:  # pragma: no cover - optional dependency not present
    OTLPSpanExporter = None  # type: ignore
try:  # Console exporter is optional; avoid when not explicitly requested
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter  # type: ignore
except Exception:  # pragma: no cover - optional dependency not present
    ConsoleSpanExporter = None  # type: ignore

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _discover_configured_exporter() -> Optional[str]:
    """Return OTLP endpoint configured in ``qmtl.yml`` when available."""

    env_override = os.getenv("QMTL_CONFIG_FILE")
    candidates: list[Path] = []
    if env_override:
        override_path = Path(env_override)
        if not override_path.is_absolute():
            override_path = Path.cwd() / override_path
        candidates.append(override_path)
    candidates.extend(Path.cwd() / name for name in ("qmtl.yml", "qmtl.yaml"))

    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
        except OSError:
            continue
        try:
            with candidate.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.debug(
                "Failed to load telemetry configuration from %s: %s", candidate, exc
            )
            continue
        if isinstance(data, dict):
            telemetry = data.get("telemetry", {})
            if isinstance(telemetry, dict):
                endpoint = telemetry.get("otel_exporter_endpoint")
                if isinstance(endpoint, str):
                    return endpoint
    return None


_INITIALISED = False


def setup_tracing(service_name: str, exporter_endpoint: Optional[str] = None) -> None:
    """Configure a global :class:`TracerProvider` if not already set."""
    global _INITIALISED
    if _INITIALISED:
        return

    endpoint = (
        exporter_endpoint
        or os.getenv("QMTL_OTEL_EXPORTER_ENDPOINT")
        or _discover_configured_exporter()
    )
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    # Exporters:
    # - If endpoint provided → use OTLP HTTP exporter
    # - Else if explicitly requested console via env value 'console' → Console exporter (when available)
    # - Else → no exporter (tests/local default) to avoid noisy/fragile shutdown warnings
    if endpoint:
        if endpoint.strip().lower() == "console" and ConsoleSpanExporter is not None:
            exporter = ConsoleSpanExporter()  # type: ignore[call-arg]
            provider.add_span_processor(BatchSpanProcessor(exporter))
        else:
            if OTLPSpanExporter is not None:  # type: ignore[truthy-bool]
                exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)  # type: ignore[call-arg]
                provider.add_span_processor(BatchSpanProcessor(exporter))
            # else: silently skip when exporter package is unavailable
    # When no exporter configured, tracing remains enabled with a provider but nothing is exported.
    # When no exporter configured, tracing remains enabled with a provider but nothing is exported.
    trace.set_tracer_provider(provider)
    _INITIALISED = True


def inject_trace_headers(headers: Dict[str, str]) -> None:
    """Inject the current span context into ``headers``."""
    inject(headers)
