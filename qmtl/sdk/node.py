from __future__ import annotations

import hashlib
import inspect
import json
import httpx

from qmtl.dagmanager import compute_node_id


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
        return compute_node_id(
            self.node_type,
            self.code_hash,
            self.config_hash,
            self.schema_hash,
        )

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


class TagQueryNode(Node):
    """Node that selects upstream queues by tag and interval."""

    def __init__(
        self,
        query_tags: list[str],
        *,
        interval: int,
        period: int,
        compute_fn=None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input=None,
            compute_fn=compute_fn,
            name=name or "tag_query",
            interval=interval,
            period=period,
            tags=list(query_tags),
        )
        self.query_tags = list(query_tags)
        self.upstreams: list[str] = []

    def resolve(self, gateway_url: str) -> list[str]:
        """Fetch matching queues from ``gateway_url``."""
        url = gateway_url.rstrip("/") + "/queues/by_tag"
        params = {"tags": ",".join(self.query_tags), "interval": self.interval}
        resp = httpx.get(url, params=params)
        resp.raise_for_status()
        queues = resp.json().get("queues", [])
        self.upstreams = queues
        return queues

    async def subscribe_updates(self, gateway_url: str) -> None:
        """Subscribe to queue updates via streaming endpoint."""
        url = gateway_url.rstrip("/") + "/queues/watch"
        params = {"tags": ",".join(self.query_tags), "interval": self.interval}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, params=params) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    queues = data.get("queues")
                    if queues is not None:
                        self.upstreams = queues

