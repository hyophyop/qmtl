from __future__ import annotations

"""OpenTelemetry tracing utilities for QMTL.

This module exposes a ``setup_tracing`` helper which configures the global
tracer provider. Traces can be exported to an OTLP compatible backend such as
Jaeger or Tempo by setting the ``QMTL_OTEL_EXPORTER_ENDPOINT`` environment
variable. When unset, spans are logged to the console which is useful for
local development.
"""

import os
from typing import Optional, Dict

from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
try:
    # Optional dependency; only needed when an OTLP endpoint is configured
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
except Exception:  # pragma: no cover - optional dependency not present
    OTLPSpanExporter = None  # type: ignore
try:  # Console exporter is optional; avoid when not explicitly requested
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter  # type: ignore
except Exception:  # pragma: no cover - optional dependency not present
    ConsoleSpanExporter = None  # type: ignore

_INITIALISED = False


def setup_tracing(service_name: str, exporter_endpoint: Optional[str] = None) -> None:
    """Configure a global :class:`TracerProvider` if not already set."""
    global _INITIALISED
    if _INITIALISED:
        return

    endpoint = exporter_endpoint or os.getenv("QMTL_OTEL_EXPORTER_ENDPOINT")
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
