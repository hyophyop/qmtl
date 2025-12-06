"""Persistent storage backend for WorldService using SQL + Redis."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import aiosqlite
import asyncpg  # type: ignore[import-untyped]

from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.services.worldservice.policy_engine import Policy

from .constants import DEFAULT_EDGE_OVERRIDES
from .models import AllocationRun, AllocationState, WorldActivation
from .repositories import (
    PersistentActivationRepository,
    PersistentBindingRepository,
    PersistentPolicyRepository,
    PersistentWorldRepository,
    _REASON_UNSET,
    _normalize_execution_domain,
    _normalize_world_node_status,
)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class _BaseDriver:
    def convert(self, query: str) -> str:
        return query

    async def execute(self, query: str, *params: Any) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def fetchone(self, query: str, *params: Any) -> Optional[Sequence[Any]]:
        raise NotImplementedError

    async def fetchall(self, query: str, *params: Any) -> List[Sequence[Any]]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class _SqliteDriver(_BaseDriver):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = aiosqlite.Row
        self._lock = asyncio.Lock()

    async def execute(self, query: str, *params: Any) -> None:
        async with self._lock:
            await self._conn.execute(query, params)
            await self._conn.commit()

    async def fetchone(self, query: str, *params: Any) -> Optional[Sequence[Any]]:
        async with self._lock:
            cursor = await self._conn.execute(query, params)
            row = await cursor.fetchone()
        return row

    async def fetchall(self, query: str, *params: Any) -> List[Sequence[Any]]:
        async with self._lock:
            cursor = await self._conn.execute(query, params)
            rows = await cursor.fetchall()
        return list(rows)

    async def close(self) -> None:
        async with self._lock:
            await self._conn.close()


class _PostgresDriver(_BaseDriver):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def convert(self, query: str) -> str:
        counter = 0
        chunks: list[str] = []
        for char in query:
            if char == "?":
                counter += 1
                chunks.append(f"${counter}")
            else:
                chunks.append(char)
        return "".join(chunks)

    async def execute(self, query: str, *params: Any) -> None:
        stmt = self.convert(query)
        async with self._pool.acquire() as conn:
            await conn.execute(stmt, *params)

    async def fetchone(self, query: str, *params: Any) -> Optional[Sequence[Any]]:
        stmt = self.convert(query)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(stmt, *params)
        return row

    async def fetchall(self, query: str, *params: Any) -> List[Sequence[Any]]:
        stmt = self.convert(query)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(stmt, *params)
        return list(rows)

    async def close(self) -> None:
        await self._pool.close()


class PersistentStorage:
    """SQL + Redis backed implementation of the WorldService storage API."""

    def __init__(self, driver: _BaseDriver, redis_client) -> None:
        self._driver = driver
        self._redis = redis_client
        self._world_repo = PersistentWorldRepository(self._driver, self._append_audit)
        self._policy_repo = PersistentPolicyRepository(self._driver, self._append_audit)
        self._binding_repo = PersistentBindingRepository(self._driver, self._append_audit)
        self._activation_repo = PersistentActivationRepository(
            self._redis, self._append_audit
        )
        self.apply_runs: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    async def create(
        cls,
        *,
        db_dsn: str,
        redis_client,
    ) -> "PersistentStorage":
        driver: _BaseDriver
        if db_dsn.startswith("postgres://") or db_dsn.startswith("postgresql://"):
            pool = await asyncpg.create_pool(db_dsn)
            driver = _PostgresDriver(pool)
        else:
            if db_dsn.startswith("sqlite:///"):
                path = db_dsn[len("sqlite:///") :]
            elif db_dsn.startswith("sqlite://"):
                path = db_dsn[len("sqlite://") :]
            else:
                path = db_dsn
            if path == ":memory:":
                conn = await aiosqlite.connect(path)
            else:
                directory = os.path.dirname(path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                conn = await aiosqlite.connect(path)
            driver = _SqliteDriver(conn)

        storage = cls(driver, redis_client)
        await storage._migrate()
        return storage

    async def close(self) -> None:
        await self._driver.close()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------
    async def _migrate(self) -> None:
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS worlds (
                id TEXT PRIMARY KEY,
                data JSON
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS policies (
                world_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                payload JSON NOT NULL,
                PRIMARY KEY (world_id, version)
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS policy_defaults (
                world_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS bindings (
                world_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                PRIMARY KEY (world_id, strategy_id)
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                world_id TEXT PRIMARY KEY,
                strategies JSON NOT NULL
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id TEXT NOT NULL,
                entry JSON NOT NULL
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS edge_overrides (
                world_id TEXT NOT NULL,
                src_node_id TEXT NOT NULL,
                dst_node_id TEXT NOT NULL,
                active INTEGER NOT NULL,
                reason TEXT,
                PRIMARY KEY (world_id, src_node_id, dst_node_id)
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_cache (
                eval_key TEXT PRIMARY KEY,
                world_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                execution_domain TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                code_version TEXT NOT NULL,
                resource_policy TEXT NOT NULL,
                result TEXT NOT NULL,
                metrics JSON NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS world_nodes (
                world_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                execution_domain TEXT NOT NULL,
                status TEXT NOT NULL,
                last_eval_key TEXT,
                annotations JSON,
                PRIMARY KEY (world_id, node_id, execution_domain)
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS history_metadata (
                world_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                as_of TEXT,
                updated_at TEXT NOT NULL,
                payload JSON NOT NULL,
                PRIMARY KEY (world_id, strategy_id)
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS world_allocations (
                world_id TEXT PRIMARY KEY,
                allocation REAL NOT NULL,
                run_id TEXT,
                etag TEXT,
                strategy_alloc_total JSON,
                updated_at TEXT NOT NULL
            )
            """
        )
        await self._driver.execute(
            """
            CREATE TABLE IF NOT EXISTS allocation_runs (
                run_id TEXT PRIMARY KEY,
                etag TEXT NOT NULL,
                payload JSON NOT NULL,
                executed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

    # ------------------------------------------------------------------
    # World lifecycle
    # ------------------------------------------------------------------
    async def create_world(self, world: Dict[str, Any]) -> None:
        await self._world_repo.create(world)
        await self.ensure_default_edge_overrides(world["id"])

    async def list_worlds(self) -> List[Dict[str, Any]]:
        return await self._world_repo.list()

    async def get_world(self, world_id: str) -> Optional[Dict[str, Any]]:
        return await self._world_repo.get(world_id)

    async def update_world(self, world_id: str, data: Dict[str, Any]) -> None:
        invalidate = {
            "contract_id",
            "dataset_fingerprint",
            "resource_policy",
            "code_version",
        } & data.keys()
        await self._world_repo.update(world_id, data)
        if invalidate:
            await self.invalidate_validation_cache(world_id)

    async def delete_world(self, world_id: str) -> None:
        await self._world_repo.delete(world_id)
        await self._policy_repo.delete_all(world_id)
        await self._binding_repo.clear(world_id)
        await self._driver.execute("DELETE FROM audit_logs WHERE world_id = ?", world_id)
        await self._driver.execute("DELETE FROM edge_overrides WHERE world_id = ?", world_id)
        await self._driver.execute("DELETE FROM validation_cache WHERE world_id = ?", world_id)
        await self._driver.execute("DELETE FROM world_nodes WHERE world_id = ?", world_id)
        await self._driver.execute("DELETE FROM history_metadata WHERE world_id = ?", world_id)
        await self._activation_repo.clear(world_id)

    # ------------------------------------------------------------------
    # Policies
    # ------------------------------------------------------------------
    async def add_policy(self, world_id: str, policy: Any) -> int:
        next_version = await self._policy_repo.add(world_id, policy)
        await self.invalidate_validation_cache(world_id)
        return next_version

    async def list_policies(self, world_id: str) -> List[Dict[str, int]]:
        return await self._policy_repo.list_versions(world_id)

    async def get_policy(self, world_id: str, version: int) -> Optional[Any]:
        return await self._policy_repo.get(world_id, version)

    async def set_default_policy(self, world_id: str, version: int) -> None:
        await self._policy_repo.set_default(world_id, version)
        await self._world_repo.update(world_id, {"default_policy_version": version})
        await self.invalidate_validation_cache(world_id)

    async def get_default_policy(self, world_id: str) -> Optional[Any]:
        return await self._policy_repo.get_default(world_id)

    async def default_policy_version(self, world_id: str) -> int:
        return await self._policy_repo.default_version(world_id)

    # ------------------------------------------------------------------
    # Bindings & decisions
    # ------------------------------------------------------------------
    async def add_bindings(self, world_id: str, strategies: Iterable[str]) -> None:
        await self._binding_repo.add(world_id, strategies)

    async def list_bindings(self, world_id: str) -> List[str]:
        return await self._binding_repo.list(world_id)

    async def set_decisions(self, world_id: str, strategies: List[str]) -> None:
        await self._binding_repo.set_decisions(world_id, strategies)

    async def get_decisions(self, world_id: str) -> List[str]:
        return await self._binding_repo.get_decisions(world_id)

    # ------------------------------------------------------------------
    # Activation state (Redis backed)
    # ------------------------------------------------------------------
    async def get_activation(
        self, world_id: str, strategy_id: str | None = None, side: str | None = None
    ) -> Dict[str, Any]:
        return await self._activation_repo.get(
            world_id, strategy_id=strategy_id, side=side
        )

    async def snapshot_activation(self, world_id: str) -> WorldActivation:
        return await self._activation_repo.snapshot(world_id)

    async def restore_activation(self, world_id: str, snapshot: WorldActivation) -> None:
        await self._activation_repo.restore(world_id, snapshot)

    async def update_activation(self, world_id: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        return await self._activation_repo.update(world_id, payload)

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------
    async def record_apply_stage(
        self, world_id: str, run_id: str, stage: str, **details: Any
    ) -> None:
        entry: Dict[str, Any] = {
            "event": "apply_stage",
            "run_id": run_id,
            "stage": stage,
            "ts": _utc_now(),
        }
        for key, value in details.items():
            if value is not None:
                entry[key] = value
        await self._append_audit(world_id, entry)

    async def get_audit(self, world_id: str) -> List[Dict[str, Any]]:
        rows = await self._driver.fetchall(
            "SELECT entry FROM audit_logs WHERE world_id = ? ORDER BY id",
            world_id,
        )
        return [json.loads(row[0]) for row in rows]

    async def _append_audit(self, world_id: str, entry: Dict[str, Any]) -> None:
        await self._driver.execute(
            "INSERT INTO audit_logs(world_id, entry) VALUES(?, ?)",
            world_id,
            json.dumps(entry),
        )

    # ------------------------------------------------------------------
    # Edge overrides
    # ------------------------------------------------------------------
    async def ensure_default_edge_overrides(self, world_id: str) -> None:
        for src, dst, reason in DEFAULT_EDGE_OVERRIDES:
            await self._driver.execute(
                "INSERT OR IGNORE INTO edge_overrides(world_id, src_node_id, dst_node_id, active, reason)"
                " VALUES(?, ?, ?, ?, ?)",
                world_id,
                src,
                dst,
                0,
                reason,
            )

    async def upsert_edge_override(
        self,
        world_id: str,
        src_node_id: str,
        dst_node_id: str,
        *,
        active: bool,
        reason: str | None | object = None,
    ) -> Dict[str, Any]:
        previous = await self.get_edge_override(world_id, src_node_id, dst_node_id)
        if reason is _REASON_UNSET:
            stored_reason = previous.get("reason") if previous is not None else None
        else:
            stored_reason = reason
        await self._driver.execute(
            "INSERT INTO edge_overrides(world_id, src_node_id, dst_node_id, active, reason)\n"
            "VALUES(?, ?, ?, ?, ?)\n"
            "ON CONFLICT(world_id, src_node_id, dst_node_id) DO UPDATE SET active = excluded.active, reason = excluded.reason",
            world_id,
            src_node_id,
            dst_node_id,
            int(active),
            stored_reason,
        )
        await self._append_audit(
            world_id,
            {
                "event": "edge_override_upserted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": active,
                "reason": stored_reason,
            },
        )
        return {
            "world_id": world_id,
            "src_node_id": src_node_id,
            "dst_node_id": dst_node_id,
            "active": bool(active),
            "reason": stored_reason,
        }

    async def get_edge_override(
        self, world_id: str, src_node_id: str, dst_node_id: str
    ) -> Optional[Dict[str, Any]]:
        row = await self._driver.fetchone(
            "SELECT active, reason FROM edge_overrides WHERE world_id = ? AND src_node_id = ? AND dst_node_id = ?",
            world_id,
            src_node_id,
            dst_node_id,
        )
        if not row:
            return None
        return {
            "world_id": world_id,
            "src_node_id": src_node_id,
            "dst_node_id": dst_node_id,
            "active": bool(row[0]),
            "reason": row[1],
        }

    async def list_edge_overrides(self, world_id: str) -> List[Dict[str, Any]]:
        rows = await self._driver.fetchall(
            "SELECT src_node_id, dst_node_id, active, reason FROM edge_overrides WHERE world_id = ? ORDER BY src_node_id, dst_node_id",
            world_id,
        )
        return [
            {
                "world_id": world_id,
                "src_node_id": row[0],
                "dst_node_id": row[1],
                "active": bool(row[2]),
                "reason": row[3],
            }
            for row in rows
        ]

    async def delete_edge_override(
        self, world_id: str, src_node_id: str, dst_node_id: str
    ) -> None:
        await self._driver.execute(
            "DELETE FROM edge_overrides WHERE world_id = ? AND src_node_id = ? AND dst_node_id = ?",
            world_id,
            src_node_id,
            dst_node_id,
        )

    # ------------------------------------------------------------------
    # Validation cache
    # ------------------------------------------------------------------
    async def get_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str,
        execution_domain: str,
        contract_id: str,
        dataset_fingerprint: str,
        code_version: str,
        resource_policy: str,
    ) -> Optional[Any]:
        domain = _normalize_execution_domain(execution_domain)
        row = await self._driver.fetchone(
            "SELECT eval_key, node_id, execution_domain, contract_id, dataset_fingerprint, code_version, resource_policy, result, metrics, timestamp\n"
            "FROM validation_cache WHERE world_id = ? AND node_id = ? AND execution_domain = ? AND contract_id = ? AND dataset_fingerprint = ? AND code_version = ? AND resource_policy = ?",
            world_id,
            node_id,
            domain,
            contract_id,
            dataset_fingerprint,
            code_version,
            resource_policy,
        )
        if not row:
            return None
        return {
            "eval_key": row[0],
            "node_id": row[1],
            "execution_domain": row[2],
            "contract_id": row[3],
            "dataset_fingerprint": row[4],
            "code_version": row[5],
            "resource_policy": row[6],
            "result": row[7],
            "metrics": json.loads(row[8]),
            "timestamp": row[9],
        }

    async def set_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str,
        execution_domain: str,
        contract_id: str,
        dataset_fingerprint: str,
        code_version: str,
        resource_policy: str,
        result: str,
        metrics: Dict[str, Any],
        timestamp: str | None = None,
    ) -> Dict[str, Any]:
        domain = _normalize_execution_domain(execution_domain)
        eval_key = self._compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )
        stamp = timestamp or _utc_now()
        await self._driver.execute(
            "INSERT INTO validation_cache(eval_key, world_id, node_id, execution_domain, contract_id, dataset_fingerprint, code_version, resource_policy, result, metrics, timestamp)\n"
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n"
            "ON CONFLICT(eval_key) DO UPDATE SET result = excluded.result, metrics = excluded.metrics, timestamp = excluded.timestamp",
            eval_key,
            world_id,
            node_id,
            domain,
            contract_id,
            dataset_fingerprint,
            code_version,
            resource_policy,
            result,
            json.dumps(metrics),
            stamp,
        )
        await self._append_audit(
            world_id,
            {"event": "validation_cache_updated", "node_id": node_id, "execution_domain": domain},
        )
        return {
            "eval_key": eval_key,
            "node_id": node_id,
            "execution_domain": domain,
            "contract_id": contract_id,
            "dataset_fingerprint": dataset_fingerprint,
            "code_version": code_version,
            "resource_policy": resource_policy,
            "result": result,
            "metrics": dict(metrics),
            "timestamp": stamp,
        }

    async def invalidate_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str | None = None,
        execution_domain: str | None = None,
    ) -> None:
        if node_id is None and execution_domain is None:
            await self._driver.execute(
                "DELETE FROM validation_cache WHERE world_id = ?",
                world_id,
            )
            await self._append_audit(world_id, {"event": "validation_cache_invalidated"})
            return
        clauses = ["world_id = ?"]
        params: list[Any] = [world_id]
        if node_id is not None:
            clauses.append("node_id = ?")
            params.append(node_id)
        if execution_domain is not None:
            clauses.append("execution_domain = ?")
            params.append(_normalize_execution_domain(execution_domain))
        where = " AND ".join(clauses)
        await self._driver.execute(
            f"DELETE FROM validation_cache WHERE {where}",
            *params,
        )
        event: Dict[str, Any] = {"event": "validation_cache_invalidated"}
        if node_id is not None:
            event["node_id"] = node_id
        if execution_domain is not None:
            event["execution_domain"] = _normalize_execution_domain(execution_domain)
        await self._append_audit(world_id, event)

    async def upsert_history_metadata(
        self,
        world_id: str,
        strategy_id: str,
        payload: Dict[str, Any],
    ) -> None:
        record = dict(payload)
        record["strategy_id"] = strategy_id
        updated = record.get("updated_at") or _utc_now()
        record["updated_at"] = updated
        as_of = record.get("as_of")
        await self._driver.execute(
            "INSERT INTO history_metadata(world_id, strategy_id, as_of, updated_at, payload) VALUES(?, ?, ?, ?, ?)\n"
            "ON CONFLICT(world_id, strategy_id) DO UPDATE SET as_of=excluded.as_of, updated_at=excluded.updated_at, payload=excluded.payload",
            world_id,
            strategy_id,
            as_of,
            updated,
            json.dumps(record),
        )
        await self._append_audit(
            world_id,
            {
                "event": "history_metadata_upserted",
                "strategy_id": strategy_id,
                "dataset_fingerprint": record.get("dataset_fingerprint"),
                "as_of": record.get("as_of"),
                "updated_at": updated,
            },
        )

    async def list_history_metadata(self, world_id: str) -> List[Dict[str, Any]]:
        rows = await self._driver.fetchall(
            "SELECT payload FROM history_metadata WHERE world_id = ? ORDER BY strategy_id",
            world_id,
        )
        return [json.loads(row[0]) for row in rows]

    async def latest_history_metadata(self, world_id: str) -> Optional[Dict[str, Any]]:
        row = await self._driver.fetchone(
            "SELECT payload FROM history_metadata WHERE world_id = ? ORDER BY (as_of IS NULL), as_of DESC, updated_at DESC LIMIT 1",
            world_id,
        )
        if not row:
            return None
        return json.loads(row[0])

    async def record_rebalance_plan(self, payload: Dict[str, Any]) -> None:
        """Record a rebalancing plan into audit logs per world (best-effort)."""
        per_world = dict(payload.get("per_world", {}))
        for wid, plan in per_world.items():
            await self._append_audit(
                wid,
                {"event": "rebalancing_planned", "world_id": wid, "plan": plan},
            )
        await self._append_audit(
            "GLOBAL",
            {
                "event": "rebalancing_planned_global",
                "per_world_ids": sorted(per_world.keys()),
                "global_deltas": payload.get("global_deltas", []),
            },
        )

    async def record_allocation_run(
        self,
        run_id: str,
        etag: str,
        payload: Dict[str, Any],
        *,
        executed: bool = False,
    ) -> None:
        created_at = _utc_now()
        await self._driver.execute(
            """
            INSERT INTO allocation_runs(run_id, etag, payload, executed, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                etag=excluded.etag,
                payload=excluded.payload,
                executed=excluded.executed,
                created_at=excluded.created_at
            """,
            run_id,
            etag,
            json.dumps(payload),
            1 if executed else 0,
            created_at,
        )

    async def get_allocation_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        row = await self._driver.fetchone(
            "SELECT run_id, etag, payload, executed, created_at FROM allocation_runs WHERE run_id = ?",
            run_id,
        )
        if not row:
            return None
        payload = json.loads(row[2])
        return AllocationRun(
            run_id=row[0],
            etag=row[1],
            payload=payload,
            executed=bool(row[3]),
            created_at=row[4],
        ).to_dict()

    async def mark_allocation_run_executed(self, run_id: str) -> None:
        await self._driver.execute(
            "UPDATE allocation_runs SET executed = 1 WHERE run_id = ?",
            run_id,
        )

    async def set_world_allocations(
        self,
        allocations: Mapping[str, float],
        *,
        run_id: str,
        etag: str,
        strategy_allocations: Mapping[str, Mapping[str, float]] | None = None,
        updated_at: str | None = None,
    ) -> None:
        ts = updated_at or _utc_now()
        for wid, ratio in allocations.items():
            strat_total = None
            if strategy_allocations and wid in strategy_allocations:
                strat_total = json.dumps(strategy_allocations[wid])
            await self._driver.execute(
                """
                INSERT INTO world_allocations(world_id, allocation, run_id, etag, strategy_alloc_total, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(world_id) DO UPDATE SET
                    allocation=excluded.allocation,
                    run_id=excluded.run_id,
                    etag=excluded.etag,
                    strategy_alloc_total=excluded.strategy_alloc_total,
                    updated_at=excluded.updated_at
                """,
                wid,
                float(ratio),
                run_id,
                etag,
                strat_total,
                ts,
            )
            await self._append_audit(
                wid,
                {
                    "event": "world_allocation_upserted",
                    "allocation": float(ratio),
                    "run_id": run_id,
                    "etag": etag,
                    "updated_at": ts,
                    "strategy_alloc_total": json.loads(strat_total) if strat_total else None,
                },
            )

    async def get_world_allocation_state(self, world_id: str) -> Optional[AllocationState]:
        row = await self._driver.fetchone(
            """
            SELECT allocation, run_id, etag, strategy_alloc_total, updated_at
            FROM world_allocations
            WHERE world_id = ?
            """,
            world_id,
        )
        if not row:
            return None
        strat_total = json.loads(row[3]) if row[3] else None
        return AllocationState(
            world_id=world_id,
            allocation=float(row[0]),
            run_id=row[1],
            etag=row[2],
            strategy_alloc_total=strat_total,
            updated_at=row[4],
        )

    async def get_world_allocation_states(
        self, world_ids: Iterable[str] | None = None
    ) -> Dict[str, AllocationState]:
        if world_ids is None:
            rows = await self._driver.fetchall(
                """
                SELECT world_id, allocation, run_id, etag, strategy_alloc_total, updated_at
                FROM world_allocations
                """,
            )
        else:
            ids = list(world_ids)
            if not ids:
                return {}
            placeholders = ", ".join(["?" for _ in ids])
            query = (
                "SELECT world_id, allocation, run_id, etag, strategy_alloc_total, updated_at "
                "FROM world_allocations WHERE world_id IN (" + placeholders + ")"
            )
            rows = await self._driver.fetchall(query, *ids)

        result: Dict[str, AllocationState] = {}
        for row in rows:
            strat_total = json.loads(row[4]) if row[4] else None
            result[row[0]] = AllocationState(
                world_id=row[0],
                allocation=float(row[1]),
                run_id=row[2],
                etag=row[3],
                strategy_alloc_total=strat_total,
                updated_at=row[5],
            )
        return result

    def _compute_eval_key(
        self,
        *,
        node_id: str,
        world_id: str,
        execution_domain: str,
        contract_id: str,
        dataset_fingerprint: str,
        code_version: str,
        resource_policy: str,
    ) -> str:
        payload = "\x1f".join(
            [
                node_id,
                world_id,
                execution_domain,
                contract_id,
                dataset_fingerprint,
                code_version,
                resource_policy,
            ]
        ).encode()
        digest = hash_bytes(payload)
        return f"blake3:{digest}"

    # ------------------------------------------------------------------
    # World nodes
    # ------------------------------------------------------------------
    async def upsert_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
        status: str | None = None,
        last_eval_key: str | None = None,
        annotations: Any | None = None,
    ) -> Dict[str, Any]:
        domain = _normalize_execution_domain(execution_domain)
        resolved_status = _normalize_world_node_status(status)
        await self._driver.execute(
            "INSERT INTO world_nodes(world_id, node_id, execution_domain, status, last_eval_key, annotations)\n"
            "VALUES(?, ?, ?, ?, ?, ?)\n"
            "ON CONFLICT(world_id, node_id, execution_domain) DO UPDATE SET status = excluded.status, last_eval_key = excluded.last_eval_key, annotations = excluded.annotations",
            world_id,
            node_id,
            domain,
            resolved_status,
            last_eval_key,
            json.dumps(annotations) if annotations is not None else None,
        )
        await self._append_audit(
            world_id,
            {
                "event": "world_node_upserted",
                "node_id": node_id,
                "execution_domain": domain,
                "status": resolved_status,
            },
        )
        return {
            "world_id": world_id,
            "node_id": node_id,
            "execution_domain": domain,
            "status": resolved_status,
            "last_eval_key": last_eval_key,
            "annotations": annotations,
        }

    async def get_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        domain = _normalize_execution_domain(execution_domain)
        row = await self._driver.fetchone(
            "SELECT status, last_eval_key, annotations FROM world_nodes WHERE world_id = ? AND node_id = ? AND execution_domain = ?",
            world_id,
            node_id,
            domain,
        )
        if not row:
            return None
        annotations = json.loads(row[2]) if row[2] else None
        return {
            "world_id": world_id,
            "node_id": node_id,
            "execution_domain": domain,
            "status": row[0],
            "last_eval_key": row[1],
            "annotations": annotations,
        }

    async def list_world_nodes(
        self,
        world_id: str,
        *,
        execution_domain: str | None = None,
    ) -> List[Dict[str, Any]]:
        if execution_domain is None:
            rows = await self._driver.fetchall(
                "SELECT node_id, execution_domain, status, last_eval_key, annotations FROM world_nodes WHERE world_id = ?",
                world_id,
            )
        else:
            domain = _normalize_execution_domain(execution_domain)
            rows = await self._driver.fetchall(
                "SELECT node_id, execution_domain, status, last_eval_key, annotations FROM world_nodes WHERE world_id = ? AND execution_domain = ?",
                world_id,
                domain,
            )
        result: List[Dict[str, Any]] = []
        for row in rows:
            annotations = json.loads(row[4]) if row[4] else None
            result.append(
                {
                    "world_id": world_id,
                    "node_id": row[0],
                    "execution_domain": row[1],
                    "status": row[2],
                    "last_eval_key": row[3],
                    "annotations": annotations,
                }
            )
        return result

    async def delete_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> None:
        if execution_domain is None:
            await self._driver.execute(
                "DELETE FROM world_nodes WHERE world_id = ? AND node_id = ?",
                world_id,
                node_id,
            )
        else:
            domain = _normalize_execution_domain(execution_domain)
            await self._driver.execute(
                "DELETE FROM world_nodes WHERE world_id = ? AND node_id = ? AND execution_domain = ?",
                world_id,
                node_id,
                domain,
            )


__all__ = ["PersistentStorage"]
