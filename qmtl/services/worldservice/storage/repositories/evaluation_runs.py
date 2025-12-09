"""Persistent repository for evaluation runs."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..models import EvaluationRunRecord
from .base import AuditLogger, DatabaseDriver


class PersistentEvaluationRunRepository:
    """SQL-backed store for evaluation runs."""

    def __init__(self, driver: DatabaseDriver, audit: AuditLogger) -> None:
        self._driver = driver
        self._audit = audit

    async def upsert(self, record: EvaluationRunRecord) -> None:
        payload = record.to_dict()
        await self._driver.execute(
            """
            INSERT INTO evaluation_runs(
                world_id,
                strategy_id,
                run_id,
                stage,
                risk_tier,
                payload,
                created_at,
                updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(world_id, strategy_id, run_id) DO UPDATE SET
                stage=excluded.stage,
                risk_tier=excluded.risk_tier,
                payload=excluded.payload,
                updated_at=excluded.updated_at
            """,
            record.world_id,
            record.strategy_id,
            record.run_id,
            record.stage,
            record.risk_tier,
            json.dumps(payload),
            record.created_at,
            record.updated_at,
        )
        await self._audit(
            record.world_id,
            {
                "event": "evaluation_run_recorded",
                "strategy_id": record.strategy_id,
                "run_id": record.run_id,
                "stage": record.stage,
                "risk_tier": record.risk_tier,
            },
        )

    async def get(
        self, world_id: str, strategy_id: str, run_id: str
    ) -> Optional[EvaluationRunRecord]:
        row = await self._driver.fetchone(
            "SELECT payload FROM evaluation_runs WHERE world_id = ? AND strategy_id = ? AND run_id = ?",
            world_id,
            strategy_id,
            run_id,
        )
        if not row:
            return None
        payload = json.loads(row[0])
        return EvaluationRunRecord.from_payload(payload)

    async def list(
        self, *, world_id: str | None = None, strategy_id: str | None = None
    ) -> List[EvaluationRunRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if world_id is not None:
            clauses.append("world_id = ?")
            params.append(world_id)
        if strategy_id is not None:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._driver.fetchall(
            f"SELECT payload FROM evaluation_runs {where_clause} ORDER BY created_at",
            *params,
        )
        return [
            EvaluationRunRecord.from_payload(json.loads(row[0]))
            for row in rows
        ]
