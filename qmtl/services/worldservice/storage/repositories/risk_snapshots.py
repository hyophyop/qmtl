"""Persistent repository for risk/portfolio snapshots."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import DatabaseDriver


class RiskSnapshotRepository:
    """SQL-backed store for portfolio/risk snapshots."""

    def __init__(self, driver: DatabaseDriver) -> None:
        self._driver = driver

    async def get(self, world_id: str, version: str) -> Optional[Dict[str, Any]]:
        row = await self._driver.fetchone(
            """
            SELECT payload FROM risk_snapshots
            WHERE world_id = ? AND version = ?
            LIMIT 1
            """,
            world_id,
            version,
        )
        if not row:
            return None
        return json.loads(row[0])

    async def upsert(self, world_id: str, payload: Dict[str, Any]) -> None:
        """Insert a snapshot with idempotent conflict handling.

        - If (world_id, version) is unused, inserts the record.
        - If it exists with the same hash, this is treated as an idempotent retry (no-op).
        - If it exists with a different hash, raise to force a new version.
        """

        version = str(payload.get("version") or "")
        if not version:
            raise ValueError("version is required")
        incoming_hash = str(payload.get("hash") or "")
        try:
            await self._driver.execute(
                """
                INSERT INTO risk_snapshots(world_id, as_of, version, payload, created_at)
                VALUES(?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                """,
                world_id,
                payload.get("as_of"),
                version,
                json.dumps(payload),
                payload.get("created_at"),
            )
            return
        except Exception:
            # Possible uniqueness conflict; compare existing hash for idempotency.
            existing = await self.get(world_id, version)
            if existing is None:
                raise
            existing_hash = str(existing.get("hash") or "")
            if existing_hash and incoming_hash and existing_hash == incoming_hash:
                return
            raise

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
