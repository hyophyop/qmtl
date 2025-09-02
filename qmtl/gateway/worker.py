from __future__ import annotations

import uuid
from typing import Awaitable, Callable, Optional

import logging
import zlib
import redis.asyncio as redis

from .database import Database
from .dagmanager_client import DagManagerClient
from .ws import WebSocketHub
from .fsm import StrategyFSM
from .redis_queue import RedisTaskQueue
from ..dagmanager.alerts import AlertManager
from .ownership import OwnershipManager
from ..dagmanager.kafka_admin import partition_key


class StrategyWorker:
    """Async worker that processes strategies from a FIFO queue."""

    def __init__(
        self,
        redis_client: redis.Redis,
        database: Database,
        fsm: StrategyFSM,
        queue: RedisTaskQueue,
        dag_client: DagManagerClient,
        ws_hub: Optional[WebSocketHub] = None,
        worker_id: Optional[str] = None,
        handler: Optional[Callable[[str], Awaitable[None]]] = None,
        alert_manager: Optional[AlertManager] = None,
        grpc_fail_threshold: int = 3,
        manager: Optional[OwnershipManager] = None,
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
        self.manager = manager or OwnershipManager(database)

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
        key_str = partition_key(strategy_id, None, None)
        key = zlib.crc32(key_str.encode())
        acquired = await self.manager.acquire(key)
        if not acquired:
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
                logging.exception("gRPC diff failed for strategy %s", strategy_id)
                self._grpc_fail_count += 1
                if self._grpc_fail_count >= self._grpc_fail_thresh:
                    if self.alerts:
                        await self.alerts.send_slack("gRPC diff repeatedly failed")
                    self._grpc_fail_count = 0
                state = await self.fsm.transition(strategy_id, "FAIL")
                if self.ws_hub:
                    await self.ws_hub.send_progress(strategy_id, state)
                return False

            if self.ws_hub:
                await self.ws_hub.send_queue_map(strategy_id, dict(diff_result.queue_map))

            if self._handler:
                await self._handler(strategy_id)

            state = await self.fsm.transition(strategy_id, "COMPLETE")
            if self.ws_hub:
                await self.ws_hub.send_progress(strategy_id, state)
            return True
        except Exception:
            logging.exception("Unhandled error processing strategy %s", strategy_id)
            state = await self.fsm.transition(strategy_id, "FAIL")
            if self.ws_hub:
                await self.ws_hub.send_progress(strategy_id, state)
            return False
        finally:
            await self.manager.release(key)

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
