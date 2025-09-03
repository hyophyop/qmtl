from __future__ import annotations

"""Schema-aware producer wrapper.

Wraps a minimal :class:`Producer` and injects a `schema_id` envelope for data
plane messages using a Schema Registry client. The envelope format is a dict:

    {"schema_id": <int>, "payload": <Any>}

This keeps JSON compatibility while allowing consumers to resolve and validate
payloads via a registry.
"""

from typing import Any

from . import Producer
from qmtl.schema.registry import SchemaRegistryClient


class SchemaAwareProducer:
    def __init__(self, inner: Producer, registry: SchemaRegistryClient | None = None) -> None:
        self._inner = inner
        # Prefer env-selected client (remote vs in-memory) when not provided
        self._registry = registry or SchemaRegistryClient.from_env()

    def register_schema(self, subject: str, schema_str: str) -> int:
        sch = self._registry.register(subject, schema_str)
        return sch.id

    def produce(self, topic: str, value: Any, *, subject: str | None = None, schema: str | None = None) -> None:
        subj = subject or topic
        sch = self._registry.latest(subj)
        if sch is None:
            if schema is None:
                raise ValueError("schema required for first publish to subject")
            sch = self._registry.register(subj, schema)
        envelope = {"schema_id": sch.id, "payload": value}
        self._inner.produce(topic, envelope)

    def flush(self) -> None:
        self._inner.flush()


__all__ = ["SchemaAwareProducer"]
