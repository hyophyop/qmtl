"""Persistent repository for policy management."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

from qmtl.services.worldservice.policy_engine import Policy

from .base import AuditLogger, DatabaseDriver


class PersistentPolicyRepository:
    """Encapsulates policy persistence concerns."""

    def __init__(self, driver: DatabaseDriver, audit: AuditLogger) -> None:
        self._driver = driver
        self._audit = audit

    async def add(self, world_id: str, policy: Any) -> int:
        row = await self._driver.fetchone(
            "SELECT MAX(version) FROM policies WHERE world_id = ?",
            world_id,
        )
        next_version = (row[0] or 0) + 1 if row else 1
        payload = self._coerce_policy(policy)
        await self._driver.execute(
            "INSERT INTO policies(world_id, version, payload) VALUES(?, ?, ?)",
            world_id,
            next_version,
            json.dumps(payload),
        )
        default = await self._driver.fetchone(
            "SELECT version FROM policy_defaults WHERE world_id = ?",
            world_id,
        )
        if default is None:
            await self._driver.execute(
                "INSERT INTO policy_defaults(world_id, version) VALUES(?, ?)",
                world_id,
                next_version,
            )
        await self._audit(world_id, {"event": "policy_added", "version": next_version})
        return next_version

    async def list_versions(self, world_id: str) -> list[Dict[str, int]]:
        rows = await self._driver.fetchall(
            "SELECT version FROM policies WHERE world_id = ? ORDER BY version",
            world_id,
        )
        return [{"version": int(row[0])} for row in rows]

    async def get(self, world_id: str, version: int) -> Optional[Policy]:
        row = await self._driver.fetchone(
            "SELECT payload FROM policies WHERE world_id = ? AND version = ?",
            world_id,
            version,
        )
        if not row:
            return None
        payload = json.loads(row[0])
        return Policy.model_validate(payload)

    async def set_default(self, world_id: str, version: int) -> None:
        await self._driver.execute(
            "INSERT INTO policy_defaults(world_id, version) VALUES(?, ?)\n"
            "ON CONFLICT(world_id) DO UPDATE SET version = excluded.version",
            world_id,
            version,
        )
        await self._audit(world_id, {"event": "policy_default_set", "version": version})

    async def get_default(self, world_id: str) -> Optional[Policy]:
        version = await self.default_version(world_id)
        if version == 0:
            return None
        return await self.get(world_id, version)

    async def default_version(self, world_id: str) -> int:
        row = await self._driver.fetchone(
            "SELECT version FROM policy_defaults WHERE world_id = ?",
            world_id,
        )
        return int(row[0]) if row else 0

    async def delete_all(self, world_id: str) -> None:
        await self._driver.execute("DELETE FROM policies WHERE world_id = ?", world_id)
        await self._driver.execute("DELETE FROM policy_defaults WHERE world_id = ?", world_id)

    def _coerce_policy(self, policy: Any) -> Dict[str, Any]:
        if hasattr(policy, "model_dump"):
            return policy.model_dump()
        if hasattr(policy, "dict"):
            return policy.dict()
        if isinstance(policy, dict):
            return dict(policy)
        return asdict(policy)
