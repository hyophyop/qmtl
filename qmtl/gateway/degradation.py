from __future__ import annotations

import asyncio
from enum import IntEnum
from typing import Optional

from .database import Database

import psutil

from . import metrics


class DegradationLevel(IntEnum):
    NORMAL = 0
    PARTIAL = 1
    MINIMAL = 2
    STATIC = 3


class DegradationManager:
    """Monitor dependency health and expose degradation level."""

    def __init__(
        self,
        redis_client,
        database,
        dag_client,
        world_client=None,
        *,
        check_interval: float = 5.0,
    ) -> None:
        self.redis = redis_client
        self.database = database
        self.dag_client = dag_client
        self.world_client = world_client
        self.check_interval = check_interval
        self.level = DegradationLevel.NORMAL
        self.redis_ok = True
        self.db_ok = True
        self.dag_ok = True
        self.world_ok = True
        self.local_queue: list[str] = []
        self._task: Optional[asyncio.Task] = None
        self._gauge = metrics.degrade_level.labels(service="gateway")
        self._gauge.set(self.level.value)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _check_dependencies(self) -> None:
        healthy_attr = getattr(self.database, "healthy", None)
        func = getattr(healthy_attr, "__func__", None)

        async def check_redis() -> bool:
            try:
                return await self.redis.ping()
            except Exception:
                return False

        async def check_db() -> bool:
            if healthy_attr is not None and func is not Database.healthy:
                try:
                    return await healthy_attr()
                except Exception:
                    return False
            return True

        async def check_dag() -> bool:
            try:
                return await self.dag_client.status()
            except Exception:
                return False

        async def check_world() -> bool:
            if self.world_client is None:
                return True
            try:
                return await self.world_client.status()
            except Exception:
                return False

        (
            self.redis_ok,
            self.db_ok,
            self.dag_ok,
            self.world_ok,
        ) = await asyncio.gather(
            check_redis(), check_db(), check_dag(), check_world()
        )

    async def evaluate(self) -> DegradationLevel:
        await self._check_dependencies()
        cpu = psutil.cpu_percent(interval=None)
        failures = sum(
            not f for f in (self.redis_ok, self.db_ok, self.dag_ok, self.world_ok)
        )
        if cpu > 95 or failures >= 3:
            return DegradationLevel.STATIC
        if cpu > 85 or failures >= 2:
            return DegradationLevel.MINIMAL
        if failures >= 1:
            return DegradationLevel.PARTIAL
        return DegradationLevel.NORMAL

    async def _flush_local_queue(self) -> None:
        if not self.local_queue or not self.dag_ok or not self.redis_ok:
            return
        try:
            await self.redis.rpush("strategy_queue", *self.local_queue)
        except Exception:
            return
        self.local_queue.clear()

    async def update(self) -> None:
        new_level = await self.evaluate()
        await self._flush_local_queue()
        if new_level != self.level:
            self.level = new_level
            self._gauge.set(new_level.value)

    async def _loop(self) -> None:
        try:
            while True:
                await self.update()
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            pass


__all__ = ["DegradationManager", "DegradationLevel"]
