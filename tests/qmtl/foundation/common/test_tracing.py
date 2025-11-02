from __future__ import annotations
from pathlib import Path

import pytest

from qmtl.foundation.common import tracing


class _Recorder:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def set(self, key: str, value: object) -> None:
        self.data[key] = value


def test_resolve_exporter_endpoint_explicit() -> None:
    assert tracing._resolve_exporter_endpoint("  http://collector  ", None) == "http://collector"


def test_resolve_exporter_endpoint_from_config(tmp_path: Path) -> None:
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        """
telemetry:
  otel_exporter_endpoint: http://localhost:4318/v1/traces
""",
        encoding="utf-8",
    )

    resolved = tracing._resolve_exporter_endpoint(None, str(config_path))
    assert resolved == "http://localhost:4318/v1/traces"


def test_resolve_exporter_endpoint_missing_config(tmp_path: Path) -> None:
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text("telemetry: {}\n", encoding="utf-8")

    resolved = tracing._resolve_exporter_endpoint(None, str(config_path))
    assert resolved is None


def test_setup_tracing_uses_console_exporter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        """
telemetry:
  otel_exporter_endpoint: console
""",
        encoding="utf-8",
    )

    recorder = _Recorder()

    class DummyProvider:
        def __init__(self, *, resource) -> None:  # type: ignore[no-untyped-def]
            recorder.set("resource", resource)
            self.processors: list[object] = []

        def add_span_processor(self, processor: object) -> None:
            self.processors.append(processor)
            recorder.set("processor", processor)

    class DummyBatchSpanProcessor:
        def __init__(self, exporter: object) -> None:
            recorder.set("exporter", exporter)

    def fake_resource_create(attrs: dict[str, str]) -> dict[str, str]:
        recorder.set("resource_attrs", attrs)
        return attrs

    def fake_set_tracer_provider(provider: object) -> None:
        recorder.set("provider", provider)

    monkeypatch.setattr(tracing, "_INITIALISED", False, raising=False)
    monkeypatch.setattr(tracing, "TracerProvider", DummyProvider)
    monkeypatch.setattr(tracing, "BatchSpanProcessor", DummyBatchSpanProcessor)
    monkeypatch.setattr(tracing, "ConsoleSpanExporter", lambda: "console-exporter")
    monkeypatch.setattr(tracing.Resource, "create", classmethod(lambda cls, attrs: fake_resource_create(attrs)))
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", fake_set_tracer_provider)

    tracing.setup_tracing("demo-service", config_path=str(config_path))

    assert recorder.data["resource_attrs"] == {"service.name": "demo-service"}
    assert recorder.data["exporter"] == "console-exporter"
    assert isinstance(recorder.data["provider"], DummyProvider)
    assert recorder.data["processor"] is recorder.data["provider"].processors[0]

    # Reset global flag for other tests
    monkeypatch.setattr(tracing, "_INITIALISED", False, raising=False)
