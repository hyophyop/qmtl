from __future__ import annotations

"""OpenTelemetry tracing utilities for QMTL.

This module exposes a ``setup_tracing`` helper which configures the global
tracer provider. Traces can be exported to an OTLP compatible backend such as
Jaeger or Tempo by defining the ``telemetry.otel_exporter_endpoint`` key in the
canonical YAML configuration. Setting the value to ``console`` retains the
development-friendly behaviour of printing spans locally.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

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

logger = logging.getLogger(__name__)

_INITIALISED = False


def _load_endpoint_from_config(config_path: str | Path | None) -> str | None:
    """Return ``telemetry.otel_exporter_endpoint`` from YAML configuration."""

    from qmtl.foundation.config import find_config_file, load_config

    resolved_path: str | None
    if config_path is not None:
        resolved_path = str(config_path)
    else:
        resolved_path = find_config_file()

    if not resolved_path:
        return None

    try:
        unified = load_config(resolved_path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "Failed to load telemetry configuration from %s: %s",
            resolved_path,
            exc,
        )
        return None

    endpoint = unified.telemetry.otel_exporter_endpoint
    if not endpoint:
        return None

    normalized = str(endpoint).strip()
    return normalized or None


def _resolve_exporter_endpoint(
    exporter_endpoint: Optional[str],
    config_path: str | Path | None,
) -> Optional[str]:
    """Normalise explicit endpoint or fall back to YAML configuration."""

    if exporter_endpoint is not None:
        normalized = exporter_endpoint.strip()
        if normalized:
            return normalized
        return None

    return _load_endpoint_from_config(config_path)


def setup_tracing(
    service_name: str,
    exporter_endpoint: Optional[str] = None,
    *,
    config_path: str | Path | None = None,
) -> None:
    """Configure a global :class:`TracerProvider` if not already set."""
    global _INITIALISED
    if _INITIALISED:
        return

    endpoint = _resolve_exporter_endpoint(exporter_endpoint, config_path)
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
