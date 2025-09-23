import asyncio

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from qmtl.sdk.gateway_client import GatewayClient
from qmtl.sdk.node import Node


@pytest.mark.asyncio
async def test_post_gateway_propagates_trace(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(exporter))

    captured: dict[str, str] = {}

    class DummyClient:
        def __init__(self):
            self.headers: dict[str, str] = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            captured.update(self.headers)
            class DummyResp:
                status_code = 202
                def json(self):
                    return {"strategy_id": "trace-strategy", "queue_map": {}}
            return DummyResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: DummyClient())
    tracer = trace.get_tracer(__name__)
    client = GatewayClient()
    with tracer.start_as_current_span("parent"):
        await client.post_strategy(
            gateway_url="http://gw", dag={}, meta=None
        )
    assert "traceparent" in captured


def test_node_feed_records_span():
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(SimpleSpanProcessor(exporter))

    n = Node(interval=1, period=1)
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent"):
        n.feed("u", 1, 0, {})

    spans = exporter.get_finished_spans()
    assert any(s.name == "node.feed" for s in spans)
