from __future__ import annotations

import hashlib
import inspect
import json


class Node:
    """Represents a processing node in a strategy DAG."""

    def __init__(
        self,
        input: Node | None = None,
        compute_fn=None,
        name: str | None = None,
        interval: int | None = None,
        period: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
        schema: dict | None = None,
    ) -> None:
        self.input = input
        self.compute_fn = compute_fn
        self.name = name
        self.interval = interval
        self.period = period
        self.tags = tags or []
        self.config = config or {}
        self.schema = schema or {}
        self.execute = True
        self.queue_topic: str | None = None

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return (
            f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"
        )

    # --- hashing helpers -------------------------------------------------
    @staticmethod
    def _sha256(data: bytes) -> str:
        try:
            h = hashlib.sha256()
            h.update(data)
            return h.hexdigest()
        except Exception:
            # Fallback if sha256 unavailable
            h = hashlib.sha3_256()
            h.update(data)
            return h.hexdigest()

    @staticmethod
    def _sha3(data: bytes) -> str:
        h = hashlib.sha3_256()
        h.update(data)
        return h.hexdigest()

    @property
    def node_type(self) -> str:
        return self.__class__.__name__

    @property
    def code_hash(self) -> str:
        if self.compute_fn is None:
            return self._sha256(b"null")
        try:
            source = inspect.getsource(self.compute_fn).encode()
        except (OSError, TypeError):
            source = getattr(self.compute_fn, "__code__", None)
            if source is not None:
                source = source.co_code
            else:
                source = repr(self.compute_fn).encode()
        return self._sha256(source)

    @property
    def config_hash(self) -> str:
        data = json.dumps(self.config, sort_keys=True).encode()
        return self._sha256(data)

    @property
    def schema_hash(self) -> str:
        data = json.dumps(self.schema, sort_keys=True).encode()
        return self._sha256(data)

    @property
    def node_id(self) -> str:
        payload = "|".join(
            [self.node_type, self.code_hash, self.config_hash, self.schema_hash]
        ).encode()
        try:
            h = hashlib.sha256()
            h.update(payload)
            return h.hexdigest()
        except Exception:  # pragma: no cover - unlikely
            h = hashlib.sha3_256()
            h.update(payload)
            return h.hexdigest()

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "interval": self.interval,
            "period": self.period,
            "tags": list(self.tags),
            "inputs": [self.input.node_id] if self.input else [],
        }


class StreamInput(Node):
    """Represents an upstream data stream placeholder."""

    def __init__(self, tags: list[str] | None = None, interval: int | None = None, period: int | None = None) -> None:
        super().__init__(input=None, compute_fn=None, name="stream_input", interval=interval, period=period, tags=tags or [])

