from __future__ import annotations

import hashlib
import inspect
import json
from collections import defaultdict
from typing import Any

import numpy as np
import xarray as xr
import httpx

from qmtl.dagmanager import compute_node_id


class NodeCache:
    """4-D tensor cache ``C[u,i,p,t]`` implemented with ``xarray``."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._tensor = xr.DataArray(
            np.empty((0, 0, period, 2), dtype=object),
            dims=("u", "i", "p", "f"),
            coords={"u": [], "i": [], "p": list(range(period)), "f": ["t", "v"]},
        )

    # ------------------------------------------------------------------
    def _ensure_coords(self, u: str, interval: int) -> None:
        if u not in self._tensor.coords["u"]:
            self._tensor = self._tensor.reindex(
                u=list(self._tensor.coords["u"].values) + [u], fill_value=None
            )
        if interval not in self._tensor.coords["i"]:
            self._tensor = self._tensor.reindex(
                i=list(self._tensor.coords["i"].values) + [interval], fill_value=None
            )

    def append(self, u: str, interval: int, timestamp: int, payload: Any) -> None:
        """Insert ``payload`` with ``timestamp`` for ``(u, interval)``."""
        self._ensure_coords(u, interval)
        u_idx = int(np.where(self._tensor.coords["u"] == u)[0])
        i_idx = int(np.where(self._tensor.coords["i"] == interval)[0])
        data = self._tensor.data.copy()
        arr = data[u_idx, i_idx]
        arr = np.roll(arr, -1, axis=0)
        arr[-1, 0] = timestamp
        arr[-1, 1] = payload
        data[u_idx, i_idx] = arr
        self._tensor = xr.DataArray(data, dims=self._tensor.dims, coords=self._tensor.coords)

    # ------------------------------------------------------------------
    def ready(self) -> bool:
        if not self._tensor.coords["u"].size or not self._tensor.coords["i"].size:
            return False
        ts = self._tensor.isel(f=0).values
        return not ((ts == None).any())  # noqa: E711

    def snapshot(self) -> dict[str, dict[int, list[tuple[int, Any]]]]:
        result: dict[str, dict[int, list[tuple[int, Any]]]] = {}
        for u in self._tensor.coords["u"].values:
            result[u] = {}
            for i in self._tensor.coords["i"].values:
                slice_ = self._tensor.loc[dict(u=u, i=i)].values
                result[u][i] = [(int(t), v) for t, v in slice_ if t is not None]
        return result


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
        self.cache = NodeCache(period or 0)
        self.pre_warmup = True

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

    # --- runtime cache handling -----------------------------------------
    def feed(self, upstream_id: str, interval: int, timestamp: int, payload) -> None:
        """Insert new data into ``cache`` and trigger ``compute_fn`` when ready."""
        self.cache.append(upstream_id, interval, timestamp, payload)
        if self.pre_warmup and self.cache.ready():
            self.pre_warmup = False
        if not self.pre_warmup and self.compute_fn:
            self.compute_fn(self.cache.snapshot())

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "interval": self.interval,
            "period": self.period,
            "tags": list(self.tags),
            "inputs": [self.input.node_id] if self.input else [],
            "code_hash": self.code_hash,
            "schema_hash": self.schema_hash,
            "pre_warmup": self.pre_warmup,
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

    def resolve(self, gateway_url: str | None = None, *, offline: bool = False) -> list[str]:
        """Fetch matching queues from ``gateway_url``.

        If ``gateway_url`` is ``None`` or the request fails, an empty list is
        returned and ``upstreams`` is cleared so the node can operate in
        offline mode.
        """
        if offline or not gateway_url:
            self.upstreams = []
            return []

        url = gateway_url.rstrip("/") + "/queues/by_tag"
        params = {"tags": ",".join(self.query_tags), "interval": self.interval}
        try:
            resp = httpx.get(url, params=params)
            resp.raise_for_status()
        except httpx.RequestError:
            self.upstreams = []
            return []

        queues = resp.json().get("queues", [])
        self.upstreams = queues
        return queues

    async def subscribe_updates(self, gateway_url: str | None = None, *, offline: bool = False) -> None:
        """Subscribe to queue updates via streaming endpoint.

        If ``gateway_url`` is ``None`` or the connection fails, the method
        simply returns and the node remains in offline mode.
        """
        if offline or not gateway_url:
            return

        url = gateway_url.rstrip("/") + "/queues/watch"
        params = {"tags": ",".join(self.query_tags), "interval": self.interval}
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, params=params) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        queues = data.get("queues")
                        if queues is not None:
                            self.upstreams = queues
        except httpx.RequestError:
            # Connection issues -> operate offline
            return

