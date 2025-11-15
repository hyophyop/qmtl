"""Persistent repository for bindings and decisions."""

from __future__ import annotations

import json
from typing import Iterable, List

from .base import AuditLogger, DatabaseDriver


class PersistentBindingRepository:
    """Stores strategy bindings and decisions for worlds."""

    def __init__(self, driver: DatabaseDriver, audit: AuditLogger) -> None:
        self._driver = driver
        self._audit = audit

    async def add(self, world_id: str, strategies: Iterable[str]) -> None:
        strategies = list(strategies)
        for strategy in strategies:
            await self._driver.execute(
                "INSERT OR IGNORE INTO bindings(world_id, strategy_id) VALUES(?, ?)",
                world_id,
                strategy,
            )
        if strategies:
            await self._audit(
                world_id,
                {"event": "bindings_added", "strategies": strategies},
            )

    async def list(self, world_id: str) -> List[str]:
        rows = await self._driver.fetchall(
            "SELECT strategy_id FROM bindings WHERE world_id = ? ORDER BY strategy_id",
            world_id,
        )
        return [row[0] for row in rows]

    async def set_decisions(self, world_id: str, strategies: List[str]) -> None:
        payload = list(strategies)
        await self._driver.execute(
            "INSERT INTO decisions(world_id, strategies) VALUES(?, ?)\n"
            "ON CONFLICT(world_id) DO UPDATE SET strategies = excluded.strategies",
            world_id,
            json.dumps(payload),
        )
        await self._audit(
            world_id,
            {"event": "decisions_set", "strategies": payload},
        )

    async def get_decisions(self, world_id: str) -> List[str]:
        row = await self._driver.fetchone(
            "SELECT strategies FROM decisions WHERE world_id = ?",
            world_id,
        )
        if not row:
            return []
        return list(json.loads(row[0]))

    async def clear(self, world_id: str) -> None:
        await self._driver.execute("DELETE FROM bindings WHERE world_id = ?", world_id)
        await self._driver.execute("DELETE FROM decisions WHERE world_id = ?", world_id)
