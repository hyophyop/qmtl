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
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

_INITIALISED = False


def setup_tracing(service_name: str, exporter_endpoint: Optional[str] = None) -> None:
    """Configure a global :class:`TracerProvider` if not already set."""
    global _INITIALISED
    if _INITIALISED:
        return

    endpoint = exporter_endpoint or os.getenv("QMTL_OTEL_EXPORTER_ENDPOINT")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _INITIALISED = True


def inject_trace_headers(headers: Dict[str, str]) -> None:
    """Inject the current span context into ``headers``."""
    inject(headers)
