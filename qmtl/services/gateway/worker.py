from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, cast

import logging
import zlib
import redis.asyncio as redis

from .database import PostgresDatabase
from .dagmanager_client import DagManagerClient
from .ws import WebSocketHub
from .fsm import StrategyFSM
from .redis_queue import RedisTaskQueue
from ..dagmanager.alerts import AlertManager
from .ownership import OwnershipManager
from ..dagmanager.kafka_admin import partition_key


@dataclass
class ComputeContext:
    world_id: str | None
    execution_domain: str | None
    as_of: str | None
    partition: str | None
    dataset_fingerprint: str | None


@dataclass
class StrategyContext:
    strategy_id: str
    dag_json: str
    compute: ComputeContext


class DiffFailure(Exception):
    """Raised when a diff attempt fails."""


class StrategyWorker:
    """Async worker that processes strategies from a FIFO queue."""

    def __init__(
        self,
        redis_client: redis.Redis,
        database: PostgresDatabase,
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
            redis_ok = bool(await self.redis.ping())
        except Exception:
            redis_ok = False
        db_ok = True
        if hasattr(self.database, "healthy"):
            try:
                db_ok = bool(await self.database.healthy())
            except Exception:
                db_ok = False
        try:
            dag_ok = bool(await self.dag_client.status())
        except Exception:
            dag_ok = False
        return bool(redis_ok) and dag_ok and db_ok

    async def _process(self, strategy_id: str) -> bool:
        key = self._lock_key(strategy_id)
        acquired = await self.manager.acquire(key, owner=self.worker_id)
        if not acquired:
            return False
        try:
            await self._enter_processing(strategy_id)
            context = await self._load_context(strategy_id)
            diff_result = await self._diff_strategy(context)
            await self._broadcast_queue_map(context.strategy_id, diff_result)
            await self._invoke_handler(context.strategy_id)
            await self._complete_strategy(context.strategy_id)
            return True
        except DiffFailure:
            await self._fail_strategy(strategy_id)
            return False
        except Exception:
            await self._handle_unexpected_error(strategy_id)
            return False
        finally:
            await self.manager.release(key)

    def _lock_key(self, strategy_id: str) -> int:
        key_str = partition_key(strategy_id, None, None)
        return zlib.crc32(key_str.encode())

    async def _enter_processing(self, strategy_id: str) -> None:
        await self._transition(strategy_id, "PROCESS")

    async def _load_context(self, strategy_id: str) -> StrategyContext:
        dag_json = await cast(Awaitable[Any], self.redis.hget(f"strategy:{strategy_id}", "dag"))
        if isinstance(dag_json, bytes):
            dag_json = dag_json.decode()
        if dag_json is None:
            raise RuntimeError("dag not found")
        compute = await self._load_compute_context(strategy_id)
        return StrategyContext(strategy_id=strategy_id, dag_json=dag_json, compute=compute)

    async def _load_compute_context(self, strategy_id: str) -> ComputeContext:
        raw_context = await cast(
            Awaitable[list[Any]],
            self.redis.hmget(
                f"strategy:{strategy_id}",
                [
                    "compute_world_id",
                    "compute_execution_domain",
                    "compute_as_of",
                    "compute_partition",
                    "compute_dataset_fingerprint",
                ],
            ),
        )
        world_id, execution_domain, as_of, partition, dataset_fingerprint = (
            self._decode_field(raw_context[0]),
            self._decode_field(raw_context[1]),
            self._decode_field(raw_context[2]),
            self._decode_field(raw_context[3]),
            self._decode_field(raw_context[4]),
        )
        return ComputeContext(
            world_id=world_id,
            execution_domain=execution_domain,
            as_of=as_of,
            partition=partition,
            dataset_fingerprint=dataset_fingerprint,
        )

    def _decode_field(self, value: str | bytes | None) -> str | None:
        if isinstance(value, bytes):
            value = value.decode()
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    async def _diff_strategy(self, context: StrategyContext):
        try:
            result = await self.dag_client.diff(
                context.strategy_id,
                context.dag_json,
                world_id=context.compute.world_id,
                execution_domain=context.compute.execution_domain,
                as_of=context.compute.as_of,
                partition=context.compute.partition,
                dataset_fingerprint=context.compute.dataset_fingerprint,
            )
            self._grpc_fail_count = 0
            return result
        except Exception as exc:
            await self._record_diff_failure(context.strategy_id, exc)
            raise DiffFailure from exc

    async def _record_diff_failure(self, strategy_id: str, error: Exception) -> None:
        logging.exception(
            "gRPC diff failed for strategy %s", strategy_id, exc_info=error
        )
        self._grpc_fail_count += 1
        if self._grpc_fail_count >= self._grpc_fail_thresh:
            if self.alerts:
                await self.alerts.send_slack("gRPC diff repeatedly failed")
            self._grpc_fail_count = 0

    async def _broadcast_queue_map(self, strategy_id: str, diff_result) -> None:
        if self.ws_hub:
            await self.ws_hub.send_queue_map(strategy_id, dict(diff_result.queue_map))

    async def _invoke_handler(self, strategy_id: str) -> None:
        if self._handler:
            await self._handler(strategy_id)

    async def _complete_strategy(self, strategy_id: str) -> None:
        await self._transition(strategy_id, "COMPLETE")

    async def _fail_strategy(self, strategy_id: str) -> None:
        await self._transition(strategy_id, "FAIL")

    async def _handle_unexpected_error(self, strategy_id: str) -> None:
        logging.exception("Unhandled error processing strategy %s", strategy_id)
        await self._fail_strategy(strategy_id)

    async def _transition(self, strategy_id: str, state: str) -> None:
        new_state = await self.fsm.transition(strategy_id, state)
        await self._send_progress(strategy_id, new_state)

    async def _send_progress(self, strategy_id: str, state: str) -> None:
        if self.ws_hub:
            await self.ws_hub.send_progress(strategy_id, state)

    async def run_once(self) -> Optional[str]:
        """Pop and process a single strategy."""
        strategy_id = await self.queue.pop(owner=self.worker_id)
        if strategy_id is None:
            return None
        processed = False
        try:
            processed = await self._process(strategy_id)
            if processed:
                return strategy_id
            return None
        finally:
            await self.queue.release(strategy_id, owner=self.worker_id)
            if not processed:
                # If acquisition failed we push the strategy back onto the queue so
                # it can be retried later. This allows a worker to take over a
                # strategy once the previous owner releases its lock.
                await self.queue.push(strategy_id)

    async def close(self) -> None:
        """Close resources associated with this worker."""
        if hasattr(self.dag_client, "close"):
            await self.dag_client.close()


__all__ = ["StrategyWorker"]
