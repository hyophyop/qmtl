"""Persistent repository for world lifecycle management."""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

from .base import AuditLogger, DatabaseDriver
from ..models import WorldRecord


class PersistentWorldRepository:
    """SQL-backed CRUD operations for worlds."""

    def __init__(self, driver: DatabaseDriver, audit: AuditLogger) -> None:
        self._driver = driver
        self._audit = audit

    async def create(self, world: Mapping[str, Any]) -> Dict[str, Any]:
        record = WorldRecord.from_payload(world)
        payload = record.to_dict()
        world_id = record.id
        await self._driver.execute(
            "INSERT OR REPLACE INTO worlds(id, data) VALUES(?, ?)",
            world_id,
            json.dumps(payload),
        )
        await self._audit(world_id, {"event": "world_created", "world": payload})
        return payload

    async def list(self) -> list[Dict[str, Any]]:
        rows = await self._driver.fetchall("SELECT data FROM worlds ORDER BY id")
        result: list[Dict[str, Any]] = []
        for row in rows:
            raw: Dict[str, Any] = json.loads(row[0])
            result.append(WorldRecord.from_payload(raw).to_dict())
        return result

    async def get(self, world_id: str) -> Optional[Dict[str, Any]]:
        row = await self._driver.fetchone(
            "SELECT data FROM worlds WHERE id = ?",
            world_id,
        )
        if not row:
            return None
        data: Dict[str, Any] = json.loads(row[0])
        return WorldRecord.from_payload(data).to_dict()

    async def update(self, world_id: str, data: Mapping[str, Any]) -> Dict[str, Any]:
        current = await self.get(world_id)
        if current is None:
            raise KeyError(world_id)
        record = WorldRecord.from_payload(current)
        record.update(dict(data))
        current = record.to_dict()
        await self._driver.execute(
            "UPDATE worlds SET data = ? WHERE id = ?",
            json.dumps(current),
            world_id,
        )
        await self._audit(world_id, {"event": "world_updated", "world": current})
        return current

    async def delete(self, world_id: str) -> None:
        await self._driver.execute("DELETE FROM worlds WHERE id = ?", world_id)
