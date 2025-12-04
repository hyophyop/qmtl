from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import zlib
import httpx
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING, Any, Mapping, Iterable
import tempfile

from qmtl.foundation.common.tagquery import (
    MatchMode,
    canonical_tag_query_params,
    normalize_match_mode,
    normalize_queues,
)
from qmtl.runtime.sdk._message_registry import AsyncMessageRegistry
from qmtl.runtime.sdk._normalizers import extract_message_payload

from .ws_client import WebSocketClient
from . import runtime, configuration, metrics as sdk_metrics

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .node import TagQueryNode


class TagQueryManager:
    """Manage :class:`TagQueryNode` instances and deliver updates.

    Queue updates are received via the ControlBus-backed WebSocket from
    ``/events/subscribe``.
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        *,
        ws_client: WebSocketClient | None = None,
        world_id: str | None = None,
        strategy_id: str | None = None,
        cache_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.gateway_url = gateway_url
        self.client = ws_client
        if self.client is not None:
            self.client.on_message = self.handle_message
        self.world_id = world_id
        self.strategy_id = strategy_id
        self._nodes: Dict[Tuple[Tuple[str, ...], int, MatchMode], List[TagQueryNode]] = {}
        self._poll_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._started = False
        # Best-effort idempotency for queue_update events: remember last
        # applied queue set per (tags, interval, match_mode) key to drop
        # duplicates that may occur during reconnects/retries.
        self._last_queue_sets: Dict[
            Tuple[Tuple[str, ...], int, MatchMode], frozenset[str]
        ] = {}
        self._message_registry = AsyncMessageRegistry()
        self._register_handlers()
        if cache_path is None:
            cfg = configuration.get_runtime_config()
            cache_path = (
                cfg.cache.tagquery_cache_path if cfg is not None else ".qmtl_tagmap.json"
            )
        self.cache_path = Path(cache_path)

    # ------------------------------------------------------------------
    @staticmethod
    def _key_str(key: Tuple[Tuple[str, ...], int, MatchMode]) -> str:
        tags, interval, mode = key
        return f"{','.join(tags)}|{interval}|{mode.value}"

    @staticmethod
    def _compute_crc(mappings: Dict[str, list[str]]) -> int:
        payload = json.dumps(mappings, sort_keys=True).encode()
        return zlib.crc32(payload) & 0xFFFFFFFF

    def _load_cache(self) -> Dict[str, list[str]]:
        try:
            data = json.loads(self.cache_path.read_text())
            mappings = data.get("mappings", {})
            crc = data.get("crc32")
            if crc != self._compute_crc(mappings):
                return {}
            return {str(k): list(v) for k, v in mappings.items()}
        except Exception:
            return {}

    def _write_cache(self, mappings: Dict[str, list[str]]) -> None:
        obj = {
            "version": 1,
            "mappings": mappings,
            "crc32": self._compute_crc(mappings),
        }
        # Best-effort atomic write to reduce risk of partial files
        try:
            payload = json.dumps(obj, sort_keys=True)
            parent = self.cache_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=parent, delete=False) as tf:
                tmp_name = tf.name
                tf.write(payload)
            os.replace(tmp_name, self.cache_path)
        except Exception:
            # Swallow errors: cache is an optimization only
            try:
                # Clean up temporary file if replace failed
                if "tmp_name" in locals() and os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except Exception:
                pass

    def _register_handlers(self) -> None:
        self._message_registry.register("tagquery.upsert", self._handle_tagquery_upsert)
        self._message_registry.register("queue_update", self._handle_queue_update)

    def _classify_tagquery_error(self, exc: Exception) -> str:
        text = str(exc).lower()
        if "interval" in text:
            return "missing_interval"
        if "tag" in text:
            return "missing_tags"
        return "invalid_spec"

    def _canonical_key(
        self,
        tags: Iterable[str] | str | None,
        interval: Any,
        match_mode: MatchMode | str | None,
    ) -> Tuple[Tuple[str, ...], int, MatchMode]:
        spec = canonical_tag_query_params(
            tags,
            interval=interval,
            match_mode=match_mode,
            require_tags=True,
            require_interval=True,
        )
        normalized_mode = normalize_match_mode(spec.get("match_mode"))
        interval_val = int(spec.get("interval") or 0)
        query_tags = tuple(spec.get("query_tags") or ())
        return query_tags, interval_val, normalized_mode

    def _canonical_key_from_payload(
        self, payload: Mapping[str, Any]
    ) -> tuple[Tuple[Tuple[str, ...], int, MatchMode] | None, str]:
        tags = payload.get("tags") or payload.get("query_tags")
        try:
            return (
                self._canonical_key(tags, payload.get("interval"), payload.get("match_mode")),
                "",
            )
        except ValueError as exc:
            return None, self._classify_tagquery_error(exc)

    def _record_update(self, outcome: str, reason: str) -> None:
        sdk_metrics.tagquery_update_total.labels(
            outcome=outcome, reason=reason or "unknown"
        ).inc()

    def _is_duplicate(self, key: Tuple[Tuple[str, ...], int, MatchMode], qset: frozenset[str]) -> bool:
        last = self._last_queue_sets.get(key)
        return last is not None and last == qset

    def _apply_update(self, key: Tuple[Tuple[str, ...], int, MatchMode], queues: list[str]) -> None:
        for n in self._nodes.get(key, []):
            n.update_queues(list(queues))

    # ------------------------------------------------------------------
    def register(self, node: TagQueryNode) -> None:
        if node.interval is None:
            raise ValueError("TagQueryNode interval is required")
        tags, interval, mode = self._canonical_key(node.query_tags, node.interval, node.match_mode)
        key = (tags, interval, mode)
        self._nodes.setdefault(key, []).append(node)

    def unregister(self, node: TagQueryNode) -> None:
        if node.interval is None:
            raise ValueError("TagQueryNode interval is required")
        tags, interval, mode = self._canonical_key(node.query_tags, node.interval, node.match_mode)
        key = (tags, interval, mode)
        lst = self._nodes.get(key)
        if lst and node in lst:
            lst.remove(node)
            if not lst:
                self._nodes.pop(key, None)

    # ------------------------------------------------------------------
    async def resolve_tags(self, *, offline: bool = False) -> None:
        """Resolve all registered nodes via the Gateway API or cache."""
        if offline or not self.gateway_url:
            cache = self._load_cache()
            for key, nodes in self._nodes.items():
                queues = cache.get(self._key_str(key), [])
                for n in nodes:
                    n.update_queues(list(queues))
            return

        url = self.gateway_url.rstrip("/") + "/queues/by_tag"
        resolved_cache: Dict[str, list[str]] = {}
        async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
            for (tags, interval, match_mode), nodes in self._nodes.items():
                params: dict[str, str | int] = {
                    "tags": ",".join(tags),
                    "interval": interval,
                    "match_mode": match_mode.value,
                    "world_id": self.world_id or "",
                }
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    raw = resp.json().get("queues", [])
                except httpx.RequestError:
                    raw = []
                queues = normalize_queues(raw)
                resolved_cache[self._key_str((tags, interval, match_mode))] = list(queues)
                for n in nodes:
                    n.update_queues(list(queues))
        if resolved_cache:
            self._write_cache(resolved_cache)

    # ------------------------------------------------------------------
    async def handle_message(self, data: dict) -> None:
        """Apply WebSocket ``data`` to registered nodes."""
        normalized = extract_message_payload(data)
        if normalized is None:
            return
        event, payload = normalized
        await self._message_registry.dispatch(event, payload)

    async def _handle_tagquery_upsert(self, payload: dict[str, Any]) -> None:
        normalized, reason = self._canonical_key_from_payload(payload)
        if normalized is None:
            self._record_update("dropped", reason or "invalid_spec")
            return
        tags, interval, _mode = normalized
        queues = normalize_queues(payload.get("queues", []))
        qset = frozenset(queues)
        applied = False
        for mode in (MatchMode.ANY, MatchMode.ALL):
            key = (tags, interval, mode)
            if self._is_duplicate(key, qset):
                self._record_update("deduped", "unchanged")
                continue
            self._last_queue_sets[key] = qset
            if self._nodes.get(key):
                self._apply_update(key, queues)
                applied = True
            else:
                self._record_update("unmatched", "no_registered_node")
        if applied:
            self._record_update("applied", "ok")

    async def _handle_queue_update(self, payload: dict[str, Any]) -> None:
        normalized, reason = self._canonical_key_from_payload(payload)
        if normalized is None:
            self._record_update("dropped", reason or "invalid_spec")
            return
        tags, interval, match_mode = normalized
        queues = normalize_queues(payload.get("queues", []))
        key = (tags, interval, match_mode)
        qset = frozenset(queues)
        if self._is_duplicate(key, qset):
            self._record_update("deduped", "unchanged")
            return
        self._last_queue_sets[key] = qset
        if not self._nodes.get(key):
            self._record_update("unmatched", "no_registered_node")
            return
        self._apply_update(key, queues)
        self._record_update("applied", "ok")

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._started and not self._poll_task_done():
            return

        if self.client:
            await self._start_client_with_polling()
            return

        if await self._subscribe_and_connect():
            return

        if self.client:
            await self._start_client_with_polling()

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
        if self._poll_task:
            self._stop_event.set()
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            finally:
                self._poll_task = None
        self._started = False

    def _poll_task_done(self) -> bool:
        if self._poll_task is None:
            return False
        if self._poll_task.done():
            self._poll_task = None
            self._started = False
            return True
        return False

    def _require_client(self) -> WebSocketClient:
        if self.client is None:
            raise RuntimeError("WebSocket client is not initialized")
        return self.client

    async def _start_client_with_polling(self) -> None:
        client = self._require_client()
        await client.start()
        if self.gateway_url:
            self._stop_event.clear()
            self._poll_task = asyncio.create_task(self._poll_loop())
        self._started = True

    async def _subscribe_and_connect(self) -> bool:
        if not self.gateway_url:
            return False

        subscribe_url = self.gateway_url.rstrip("/") + "/events/subscribe"
        try:
            async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
                topic = f"w/{self.world_id}/queues" if self.world_id else "queues"
                payload = {
                    "topics": [topic],
                    "world_id": self.world_id or "",
                    "strategy_id": self.strategy_id or "",
                }
                resp = await client.post(subscribe_url, json=payload)
                if resp.status_code != 200:
                    return False
                data = resp.json()
                stream_url = data.get("stream_url")
                token = data.get("token")
                if not stream_url:
                    return False
                self.client = WebSocketClient(
                    stream_url, on_message=self.handle_message, token=token
                )
                await self._start_client_with_polling()
                return True
        except Exception:
            return False

    async def _poll_loop(self) -> None:
        # Periodically reconcile tag queries via HTTP GET to avoid depending
        # solely on WS events. Uses the same /queues/by_tag endpoint.
        while not self._stop_event.is_set():
            try:
                await self.resolve_tags(offline=False)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=runtime.POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
