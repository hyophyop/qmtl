from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import asyncio
import json
import time

from .diff_service import DiffService, DiffRequest, NodeRepository


@dataclass
class BufferingScheduler:
    """Automatically reprocess buffered nodes after a delay."""

    repo: NodeRepository
    diff: DiffService
    interval: float = 3600.0
    delay_days: int = 7
    _task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            finally:
                self._task = None

    async def _run(self) -> None:
        try:
            while True:
                await self.check_once()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def check_once(self) -> None:
        cutoff = int((time.time() - self.delay_days * 86400) * 1000)
        node_ids = self.repo.get_buffering_nodes(cutoff)
        if not node_ids:
            return
        records = self.repo.get_nodes(node_ids)
        for nid in node_ids:
            rec = records.get(nid)
            if rec is None:
                continue
            dag = {
                "nodes": [
                    {
                        "node_id": rec.node_id,
                        "node_type": rec.node_type,
                        "code_hash": rec.code_hash,
                        "schema_hash": rec.schema_hash,
                        "interval": rec.interval,
                        "period": rec.period,
                        "tags": list(rec.tags),
                    }
                ]
            }
            dag_json = json.dumps(dag)
            self.diff.diff(DiffRequest(strategy_id=nid, dag_json=dag_json))
            self.repo.clear_buffering(nid)


__all__ = ["BufferingScheduler"]
