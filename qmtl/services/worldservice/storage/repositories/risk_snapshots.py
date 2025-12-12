"""Persistent repository for risk/portfolio snapshots."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import DatabaseDriver


class RiskSnapshotRepository:
    """SQL-backed store for portfolio/risk snapshots."""

    def __init__(self, driver: DatabaseDriver) -> None:
        self._driver = driver

    async def upsert(self, world_id: str, payload: Dict[str, Any]) -> None:
        await self._driver.execute(
            """
            INSERT INTO risk_snapshots(world_id, as_of, version, payload, created_at)
            VALUES(?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            ON CONFLICT(world_id, version) DO UPDATE SET
                as_of = excluded.as_of,
                payload = excluded.payload,
                created_at = excluded.created_at
            """,
            world_id,
            payload.get("as_of"),
            payload.get("version"),
            json.dumps(payload),
            payload.get("created_at"),
        )

    async def latest(self, world_id: str) -> Optional[Dict[str, Any]]:
        row = await self._driver.fetchone(
            """
            SELECT payload FROM risk_snapshots
            WHERE world_id = ?
            ORDER BY as_of DESC, version DESC
            LIMIT 1
            """,
            world_id,
        )
        if not row:
            return None
        return json.loads(row[0])

    async def list(self, world_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = await self._driver.fetchall(
            """
            SELECT payload FROM risk_snapshots
            WHERE world_id = ?
            ORDER BY as_of DESC, version DESC
            LIMIT ?
            """,
            world_id,
            limit,
        )
        return [json.loads(row[0]) for row in rows]


__all__ = ["RiskSnapshotRepository"]
