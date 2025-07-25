from __future__ import annotations

import uuid
from typing import Awaitable, Callable, Optional

import redis.asyncio as redis

from .database import Database
from .dagmanager_client import DagManagerClient
from .ws import WebSocketHub
from .fsm import StrategyFSM
from .queue import RedisFIFOQueue
from ..dagmanager.alerts import AlertManager


class StrategyWorker:
    """Async worker that processes strategies from a FIFO queue."""

    def __init__(
        self,
        redis_client: redis.Redis,
        database: Database,
        fsm: StrategyFSM,
        queue: RedisFIFOQueue,
        dag_client: DagManagerClient,
        ws_hub: Optional[WebSocketHub] = None,
        worker_id: Optional[str] = None,
        handler: Optional[Callable[[str], Awaitable[None]]] = None,
        alert_manager: Optional[AlertManager] = None,
        grpc_fail_threshold: int = 3,
    ) -> None:
        self.redis = redis_client
        self.database = database
        self.fsm = fsm
        self.queue = queue
        self.dag_client = dag_client
        self.ws_hub = ws_hub
        self.worker_id = worker_id or str(uuid.uuid4())
        self._handler = handler
        self.alerts = alert_manager
        self._grpc_fail_thresh = grpc_fail_threshold
        self._grpc_fail_count = 0

    async def healthy(self) -> bool:
        """Return ``True`` if all critical dependencies are reachable."""
        try:
            redis_ok = await self.redis.ping()
        except Exception:
            redis_ok = False
        db_ok = True
        if hasattr(self.database, "healthy"):
            try:
                db_ok = await self.database.healthy()
            except Exception:
                db_ok = False
        try:
            dag_ok = await self.dag_client.status()
        except Exception:
            dag_ok = False
        return bool(redis_ok) and dag_ok and db_ok

    async def _process(self, strategy_id: str) -> bool:
        lock_key = f"lock:{strategy_id}"
        locked = await self.redis.set(lock_key, self.worker_id, nx=True, px=60000)
        if not locked:
            return False
        try:
            state = await self.fsm.transition(strategy_id, "PROCESS")
            if self.ws_hub:
                await self.ws_hub.send_progress(strategy_id, state)

            dag_json = await self.redis.hget(f"strategy:{strategy_id}", "dag")
            if isinstance(dag_json, bytes):
                dag_json = dag_json.decode()
            if dag_json is None:
                raise RuntimeError("dag not found")

            try:
                diff_result = await self.dag_client.diff(strategy_id, dag_json)
                self._grpc_fail_count = 0
            except Exception:
                self._grpc_fail_count += 1
                if self._grpc_fail_count >= self._grpc_fail_thresh:
                    if self.alerts:
                        await self.alerts.send_slack("gRPC diff repeatedly failed")
                    self._grpc_fail_count = 0
                state = await self.fsm.transition(strategy_id, "FAIL")
                if self.ws_hub:
                    await self.ws_hub.send_progress(strategy_id, state)
                return True

            if self.ws_hub:
                await self.ws_hub.send_queue_map(strategy_id, dict(diff_result.queue_map))

            if self._handler:
                await self._handler(strategy_id)

            state = await self.fsm.transition(strategy_id, "COMPLETE")
            if self.ws_hub:
                await self.ws_hub.send_progress(strategy_id, state)
            return True
        except Exception:
            state = await self.fsm.transition(strategy_id, "FAIL")
            if self.ws_hub:
                await self.ws_hub.send_progress(strategy_id, state)
            return True
        finally:
            # The lock expires automatically; explicit deletion would allow
            # another worker to reprocess the same strategy immediately.
            pass

    async def run_once(self) -> Optional[str]:
        """Pop and process a single strategy."""
        strategy_id = await self.queue.pop()
        if strategy_id is None:
            return None
        await self._process(strategy_id)
        return strategy_id

    async def close(self) -> None:
        """Close resources associated with this worker."""
        if hasattr(self.dag_client, "close"):
            await self.dag_client.close()


__all__ = ["StrategyWorker"]
