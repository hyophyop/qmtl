from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from qmtl.common import compute_node_id, crc32_of_list
from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.strategy_submission import (
    StrategySubmissionConfig,
    StrategySubmissionHelper,
)


class DummyManager:
    def __init__(self) -> None:
        self.calls: list[StrategySubmit] = []

    async def submit(self, payload: StrategySubmit) -> tuple[str, bool]:
        self.calls.append(payload)
        return "strategy-abc", False


class DummyDagManager:
    def __init__(self) -> None:
        self.tag_queries: list[tuple] = []
        self.diff_calls: list[tuple] = []
        self.raise_diff: bool = False
        self.diff_result = SimpleNamespace(
            sentinel_id="diff-sentinel",
            queue_map={"node123#0": "topic-A"},
        )

    async def get_queues_by_tag(
        self, tags, interval, match_mode, world_id, execution_domain
    ):
        self.tag_queries.append((tuple(tags), interval, match_mode, world_id, execution_domain))
        return [{"queue": f"{world_id}:{tags[0]}" if world_id else f"global:{tags[0]}"}]

    async def diff(
        self,
        strategy_id,
        dag_json,
        world_id=None,
        execution_domain=None,
        as_of=None,
        partition=None,
        dataset_fingerprint=None,
    ):
        self.diff_calls.append((strategy_id, world_id, execution_domain, as_of, partition, dataset_fingerprint))
        if self.raise_diff:
            raise TimeoutError("diff timeout")
        return self.diff_result


class DummyDatabase:
    def __init__(self) -> None:
        self.bindings: list[tuple[str, str]] = []

    async def upsert_wsb(self, world_id: str, strategy_id: str) -> None:
        self.bindings.append((world_id, strategy_id))


def _build_payload(mismatch: bool = False) -> tuple[StrategySubmit, dict, str]:
    node_type = "TagQueryNode"
    code_hash = "code"
    config_hash = "config"
    schema_hash = "schema"
    expected_node_id = compute_node_id(node_type, code_hash, config_hash, schema_hash)
    node_id = "bad-node" if mismatch else expected_node_id
    dag = {
        "nodes": [
            {
                "node_id": node_id,
                "node_type": node_type,
                "code_hash": code_hash,
                "config_hash": config_hash,
                "schema_hash": schema_hash,
                "tags": ["alpha"],
                "interval": 5,
                "match_mode": "any",
            }
        ]
    }
    dag_json = base64.b64encode(json.dumps(dag).encode()).decode()
    crc = crc32_of_list([node_id])
    payload = StrategySubmit(
        dag_json=dag_json,
        meta={"execution_domain": " sim "},
        world_id="world-1",
        node_ids_crc32=crc,
    )
    return payload, dag, expected_node_id


@pytest.mark.asyncio
async def test_process_submission_uses_queries_and_diff_for_strategy():
    manager = DummyManager()
    dagmanager = DummyDagManager()
    database = DummyDatabase()
    helper = StrategySubmissionHelper(manager, dagmanager, database)
    payload, _, expected_node_id = _build_payload()

    result = await helper.process(
        payload,
        StrategySubmissionConfig(
            submit=True,
            diff_timeout=0.1,
        ),
    )

    assert result.strategy_id == "strategy-abc"
    assert result.sentinel_id == "diff-sentinel"
    assert result.queue_map.keys() == {expected_node_id}
    queues = result.queue_map[expected_node_id]
    assert queues and queues[0]["queue"] == "world-1:alpha"
    assert database.bindings == [("world-1", "strategy-abc")]
    assert dagmanager.diff_calls, "diff should be invoked for sentinel lookup"


@pytest.mark.asyncio
async def test_process_dry_run_prefers_diff_queue_map():
    dagmanager = DummyDagManager()
    helper = StrategySubmissionHelper(DummyManager(), dagmanager, DummyDatabase())
    payload, _, _ = _build_payload()

    result = await helper.process(
        payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    )

    assert result.strategy_id == "dryrun"
    assert result.queue_map == {"node123": [{"queue": "topic-A", "global": False}]}
    assert not dagmanager.tag_queries, "diff path should avoid tag query lookups"
    assert result.sentinel_id == "diff-sentinel"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        StrategySubmissionConfig(submit=True, diff_timeout=0.1),
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    ],
    ids=["submit", "dry-run"],
)
async def test_shared_validation_path(config: StrategySubmissionConfig) -> None:
    helper = StrategySubmissionHelper(DummyManager(), DummyDagManager(), DummyDatabase())
    payload, _, _ = _build_payload(mismatch=True)

    with pytest.raises(HTTPException) as exc:
        await helper.process(payload, config)

    detail = exc.value.detail
    assert detail["code"] == "E_NODE_ID_MISMATCH"


@pytest.mark.asyncio
async def test_dry_run_diff_failure_falls_back_to_queries_and_crc() -> None:
    dagmanager = DummyDagManager()
    dagmanager.raise_diff = True
    helper = StrategySubmissionHelper(DummyManager(), dagmanager, DummyDatabase())
    payload, dag, expected_node_id = _build_payload()

    result = await helper.process(
        payload,
        StrategySubmissionConfig(
            submit=False,
            strategy_id="dryrun",
            diff_timeout=0.5,
            prefer_diff_queue_map=True,
            sentinel_default="",
            diff_strategy_id="dryrun",
            use_crc_sentinel_fallback=True,
        ),
    )

    assert result.queue_map.keys() == {expected_node_id}
    assert result.queue_map[expected_node_id][0]["queue"] == "world-1:alpha"
    expected_crc = crc32_of_list(n.get("node_id", "") for n in dag.get("nodes", []))
    assert result.sentinel_id == f"dryrun:{expected_crc:08x}"
