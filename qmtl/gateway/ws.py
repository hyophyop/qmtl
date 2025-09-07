from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Optional, Set, Any, Dict

from fastapi import WebSocket

from qmtl.sdk.node import MatchMode

from ..common.cloudevents import format_event
from . import metrics


logger = logging.getLogger(__name__)


class WebSocketHub:
    """Broadcast Gateway state updates to SDK clients."""

    def __init__(self) -> None:
        self._clients: Set[Any] = set()
        self._topics: Dict[Any, Optional[Set[str]]] = {}
        self._filters: Dict[Any, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._sentinel: object = object()
        # Large default to avoid throttling in tests; backpressure policy can be tuned.
        self._queue: asyncio.Queue[object] = asyncio.Queue(maxsize=10000)
        self._task: Optional[asyncio.Task] = None
        self._server: Optional[Any] = None
        self._port: Optional[int] = None
        self._known_topics: Set[str] = set()
        # Best-effort idempotency window for duplicate event IDs
        # Tracks the last N CloudEvent ids to drop duplicates during reconnect/retry.
        from collections import deque
        self._seen_ids_order = deque(maxlen=10000)
        self._seen_ids: Set[str] = set()
        # Optional monotonic sequence for events to aid client-side reordering
        self._seq_no: int = 0
        # Per-connection token bucket (tokens/sec). 0 disables rate limiting.
        self._rate_limit_per_sec: int = 0
        self._rl_state: Dict[Any, tuple[float, float]] = {}
        # Optional env override for rate limit (tokens/sec)
        try:
            import os as _os
            _rl = _os.getenv("QMTL_WS_RATE_LIMIT")
            if _rl:
                self._rate_limit_per_sec = int(_rl)
        except Exception:
            pass

    async def start(self, *, start_server: bool = False) -> int:
        """Start the internal sender loop and a lightweight WS server.

        Returns the bound port for the ephemeral WebSocket server. FastAPI
        apps can also attach to this hub via ``/ws``; this server exists for
        test scenarios that connect directly to the hub.
        """
        if self._task is None:
            self._task = asyncio.create_task(self._sender_loop())

        # Lazily start an ephemeral ws server to satisfy tests that
        # connect directly to the hub.
        # Disabled by default to avoid leaking sockets in parallel tests.
        # Can be enabled via parameter or the QMTL_WS_ENABLE_SERVER=1 env var.
        if self._server is None:
            if not start_server:
                try:
                    import os as _os
                    if _os.getenv("QMTL_WS_ENABLE_SERVER", "0") != "1":
                        return int(self._port or 0)
                except Exception:
                    return int(self._port or 0)
            try:
                import websockets

                async def _acceptor(sock):
                    async with self._lock:
                        self._clients.add(sock)
                    try:
                        # Drain incoming messages; hub is broadcast-only
                        while True:
                            await sock.recv()
                    except Exception:
                        pass
                    finally:
                        async with self._lock:
                            self._clients.discard(sock)

                self._server = await websockets.serve(_acceptor, "127.0.0.1", 0)
                # Determine the bound port from the underlying socket
                sockets = getattr(self._server, "sockets", None) or []
                if sockets:
                    self._port = sockets[0].getsockname()[1]
                else:
                    self._port = 0
            except Exception:
                logger.exception("Failed to start internal WebSocket server")
                self._port = 0

        return int(self._port or 0)

    async def stop(self) -> None:
        """Stop the sender loop and disconnect clients."""
        await self._queue.put(self._sentinel)
        await self._queue.join()
        if self._task:
            await self._task
            self._task = None
        # Close ephemeral server if running
        if self._server is not None:
            try:
                self._server.close()
                await self._server.wait_closed()
            except Exception:
                logger.exception("Failed to stop internal WebSocket server")
            finally:
                self._server = None
                self._port = None
        async with self._lock:
            for ws in list(self._clients):
                with contextlib.suppress(Exception):
                    await ws.close()
            self._clients.clear()

    def is_running(self) -> bool:
        """Return ``True`` if the sender loop is active."""
        return self._task is not None and not self._task.done()

    async def connect(self, websocket: WebSocket, topics: Optional[Set[str]] = None) -> None:
        """Register an incoming WebSocket connection.

        If ``topics`` is provided, the connection only receives events
        matching those topic names (e.g., {"activation", "policy", "queue"}).
        ``None`` means no restriction (receive all events).
        """
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
            self._topics[websocket] = topics
            # Initialize empty filters; event handlers may populate world/strategy filters.
            self._filters.setdefault(websocket, {})
        await self._recalc_subscriber_metrics()

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._clients.discard(websocket)
            self._topics.pop(websocket, None)
            self._filters.pop(websocket, None)
            self._rl_state.pop(websocket, None)
        metrics.record_ws_drop()
        await self._recalc_subscriber_metrics()

    async def set_topics(
        self, websocket: WebSocket, topics: Optional[Set[str]]
    ) -> None:
        """Update topic subscriptions for an existing WebSocket client."""
        async with self._lock:
            if websocket in self._clients:
                self._topics[websocket] = topics
        await self._recalc_subscriber_metrics()

    async def _recalc_subscriber_metrics(self) -> None:
        """Recompute subscriber gauge metrics."""
        counts: Dict[str, int] = {}
        async with self._lock:
            all_topics: Set[str] = set(self._known_topics)
            for tset in self._topics.values():
                if tset is not None:
                    all_topics.update(tset)
            for topic in all_topics:
                count = 0
                for tset in self._topics.values():
                    if tset is None or (tset is not None and topic in tset):
                        count += 1
                counts[topic] = count
        metrics.update_ws_subscribers(counts)

    async def set_filters(
        self,
        websocket: Any,
        *,
        world_id: str | None = None,
        strategy_id: str | None = None,
        scopes: Set[str] | None = None,
    ) -> None:
        """Attach scope filters to a connected client."""
        async with self._lock:
            if websocket in self._clients:
                filt = self._filters.setdefault(websocket, {})
                if world_id is not None:
                    filt["world_id"] = world_id
                if strategy_id is not None:
                    filt["strategy_id"] = strategy_id
                if scopes is not None:
                    filt["scopes"] = set(scopes)
    async def _sender_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is self._sentinel:
                self._queue.task_done()
                break
            # Support both (message, topic) tuples and raw message strings
            if isinstance(item, tuple) and len(item) == 2:
                msg, topic = item  # type: ignore[misc]
            else:
                msg, topic = item, None
            # Idempotency: drop duplicates by CloudEvent.id when present
            try:
                parsed_any = json.loads(msg if isinstance(msg, str) else msg)
                if isinstance(parsed_any, dict):
                    ev_id = parsed_any.get("id")
                    if isinstance(ev_id, str):
                        if ev_id in self._seen_ids:
                            metrics.record_event_dropped(topic or "unknown")
                            logger.debug(
                                "duplicate_drop",
                                extra={"event": "duplicate_drop", "id": ev_id, "topic": topic},
                            )
                            self._queue.task_done()
                            continue
                        self._seen_ids_order.append(ev_id)
                        # Keep membership set in sync with deque window
                        self._seen_ids = set(self._seen_ids_order)
            except Exception:
                pass
            async with self._lock:
                if topic is None:
                    clients = list(self._clients)
                else:
                    # First filter by topic subscription
                    clients = [
                        ws
                        for ws in self._clients
                        if self._topics.get(ws) is None or topic in (self._topics.get(ws) or set())
                    ]
            # Optional scope-based filtering: if payload includes world_id, apply it
            world_id: str | None = None
            try:
                if isinstance(msg, str):
                    parsed = json.loads(msg)
                else:
                    parsed = json.loads(msg)
                data = parsed.get("data") if isinstance(parsed, dict) else None
                if isinstance(data, dict):
                    w = data.get("world_id")
                    if isinstance(w, str):
                        world_id = w
            except Exception:
                world_id = None
            if world_id is not None and clients:
                async with self._lock:
                    clients = [
                        ws for ws in clients if (self._filters.get(ws, {}).get("world_id") in (None, world_id))
                    ]
            if topic is not None:
                self._known_topics.add(topic)
                metrics.record_event_fanout(topic, len(clients))
            if clients:
                async def _send(ws_any: Any, data: str):
                    # Simple per-connection rate limit using a token bucket.
                    if self._rate_limit_per_sec > 0:
                        now = asyncio.get_event_loop().time()
                        tokens, last = self._rl_state.get(ws_any, (float(self._rate_limit_per_sec), now))
                        # Refill proportional to elapsed time
                        elapsed = max(0.0, now - last)
                        refill = elapsed * float(self._rate_limit_per_sec)
                        tokens = min(float(self._rate_limit_per_sec), tokens + refill)
                        if tokens < 1.0:
                            # Drop under rate limit; structured log for ops visibility
                            logger.debug("ws_rate_limited_drop", extra={"event": "ws_rate_limited_drop"})
                            return None
                        tokens -= 1.0
                        self._rl_state[ws_any] = (tokens, now)
                    if hasattr(ws_any, "send_text"):
                        return await ws_any.send_text(data)
                    if hasattr(ws_any, "send"):
                        return await ws_any.send(data)
                    raise RuntimeError("Unknown websocket client type")

                results = await asyncio.gather(
                    *(_send(ws, msg) for ws in clients), return_exceptions=True
                )
                failures = []
                for client_ws, res in zip(clients, results):
                    if isinstance(res, Exception):
                        logger.warning(
                            "Failed to send message to client %s: %s",
                            getattr(client_ws, "client", None) or "unknown",
                            res,
                        )
                        failures.append(client_ws)
                if failures:
                    async with self._lock:
                        for ws in failures:
                            self._clients.discard(ws)
                            self._topics.pop(ws, None)
                    metrics.record_ws_drop(len(failures))
                    await self._recalc_subscriber_metrics()
            self._queue.task_done()

    async def broadcast(self, data: dict, *, topic: Optional[str] = None) -> None:
        """Queue ``data`` for broadcast to clients.

        If ``topic`` is provided, only clients subscribed to that topic will
        receive the message. Otherwise the message is broadcast to all.
        """
        # Inject hub-assigned monotonic seq_no if absent
        if "seq_no" not in data:
            try:
                self._seq_no += 1
                data["seq_no"] = self._seq_no
            except Exception:
                pass
        # Apply simple backpressure policy: if queue is full, drop newest message
        item = (json.dumps(data), topic)
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            # Drop and log; rely on upstream dedupe/idempotency for recovery.
            logger.warning("event_queue_full_drop", extra={"event": "event_queue_full_drop", "topic": topic})
            if topic:
                try:
                    metrics.record_event_dropped(topic)
                except Exception:
                    pass
            # Best-effort: remove one oldest item then enqueue
            with contextlib.suppress(Exception):
                _ = self._queue.get_nowait()
                self._queue.task_done()
            with contextlib.suppress(Exception):
                self._queue.put_nowait(item)
        if topic is not None and topic not in self._known_topics:
            self._known_topics.add(topic)
            await self._recalc_subscriber_metrics()

    async def send_progress(self, strategy_id: str, status: str) -> None:
        event = format_event(
            "qmtl.gateway",
            "progress",
            {"strategy_id": strategy_id, "status": status},
        )
        await self.broadcast(event)

    async def send_queue_map(
        self, strategy_id: str, queue_map: dict[str, list[str] | str]
    ) -> None:
        event = format_event(
            "qmtl.gateway",
            "queue_map",
            {"strategy_id": strategy_id, "queue_map": queue_map},
        )
        await self.broadcast(event)

    async def send_queue_update(
        self,
        tags: list[str],
        interval: int,
        queues: list[dict[str, object]],
        match_mode: MatchMode = MatchMode.ANY,
        world_id: str | None = None,
    ) -> None:
        """Broadcast queue update events.

        ``match_mode`` must be ``MatchMode.ANY`` or ``MatchMode.ALL``.
        """
        event = format_event(
            "qmtl.gateway",
            "queue_update",
            {
                "tags": tags,
                "interval": interval,
                "queues": queues,
                "match_mode": match_mode.value,
                **({"world_id": world_id} if world_id else {}),
            },
        )
        await self.broadcast(event, topic="queue")

    async def send_sentinel_weight(self, sentinel_id: str, weight: float) -> None:
        """Broadcast sentinel weight updates."""
        event = format_event(
            "qmtl.gateway",
            "sentinel_weight",
            {"sentinel_id": sentinel_id, "weight": weight},
        )
        await self.broadcast(event, topic="activation")

    async def send_activation_updated(self, payload: dict) -> None:
        """Broadcast activation updates."""
        event = format_event("qmtl.gateway", "activation_updated", payload)
        await self.broadcast(event, topic="activation")

    async def send_policy_updated(self, payload: dict) -> None:
        """Broadcast policy updates."""
        event = format_event("qmtl.gateway", "policy_updated", payload)
        await self.broadcast(event, topic="policy")


__all__ = ["WebSocketHub"]
