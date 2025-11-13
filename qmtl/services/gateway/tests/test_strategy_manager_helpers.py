from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.strategy_manager import StrategyManager


class _StubDatabase:
    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:
        return None


class _StubFSM:
    async def get(self, strategy_id: str) -> str | None:
        return None

    async def create(self, strategy_id: str, meta: dict | None) -> None:
        return None


@pytest.fixture
def strategy_manager(fake_redis):
    return StrategyManager(
        redis=fake_redis,
        database=_StubDatabase(),
        fsm=_StubFSM(),
    )


def _make_payload(dag: dict[str, object]) -> StrategySubmit:
    encoded = base64.b64encode(json.dumps(dag).encode()).decode()
    return StrategySubmit(
        dag_json=encoded,
        meta=None,
        world_id=None,
        node_ids_crc32=0,
    )


def test_parse_dag_payload_returns_hash(strategy_manager):
    dag = {"nodes": [{"node_id": "node-1"}]}
    payload = _make_payload(dag)

    dag_dict, dag_copy, dag_hash = strategy_manager._parse_dag_payload(payload)

    assert dag_dict == dag
    assert dag_copy == dag
    assert dag_copy is not dag_dict
    expected_hash = hashlib.sha256(
        json.dumps(dag, sort_keys=True).encode()
    ).hexdigest()
    assert dag_hash == expected_hash


def test_parse_dag_payload_handles_plain_json(strategy_manager):
    dag = {"nodes": [{"node_id": "node-plain"}]}
    payload = StrategySubmit(
        dag_json=json.dumps(dag),
        meta=None,
        world_id=None,
        node_ids_crc32=0,
    )

    dag_dict, _, _ = strategy_manager._parse_dag_payload(payload)

    assert dag_dict == dag


def test_inject_version_sentinel_adds_version(strategy_manager):
    dag = {"nodes": []}
    meta = {"strategy_version": " 1.2.3 "}

    updated = strategy_manager._inject_version_sentinel("strategy-1", dag, meta)

    sentinel = updated["nodes"][-1]
    assert sentinel["node_type"] == "VersionSentinel"
    assert sentinel["node_id"] == "strategy-1-sentinel"
    assert sentinel["version"] == "1.2.3"


def test_inject_version_sentinel_skips_when_disabled(fake_redis):
    manager = StrategyManager(
        redis=fake_redis,
        database=_StubDatabase(),
        fsm=_StubFSM(),
        insert_sentinel=False,
    )
    dag = {"nodes": []}

    updated = manager._inject_version_sentinel("strategy-2", dag, None)

    assert updated["nodes"] == []


def test_build_history_mapping_includes_fields(strategy_manager):
    report = SimpleNamespace(
        world_id="world-1",
        execution_domain="live",
    )

    mapping = strategy_manager._build_history_mapping(
        report, dataset_fp="fp-1", as_of_value="2025-01-01T00:00:00Z"
    )

    assert mapping == {
        "compute_world_id": "world-1",
        "compute_execution_domain": "live",
        "compute_as_of": "2025-01-01T00:00:00Z",
        "compute_dataset_fingerprint": "fp-1",
    }


class _Artifact:
    def __init__(self) -> None:
        self.dataset_fingerprint = "fp-artifact"
        self.as_of = "2025-02-01T00:00:00Z"
        self.rows = 10
        self.uri = "local://artifact"

    def model_dump(self) -> dict[str, object]:
        return {
            "dataset_fingerprint": self.dataset_fingerprint,
            "as_of": self.as_of,
            "rows": self.rows,
            "uri": self.uri,
        }


def test_build_meta_payload_matches_report(strategy_manager):
    artifact = _Artifact()
    report = SimpleNamespace(
        node_id="node-1",
        interval=60,
        rows=5,
        coverage_bounds=(0, 120),
        conformance_flags={"missing": 1},
        conformance_warnings=["gap"],
        world_id="world-9",
        execution_domain="sim",
    )

    payload = strategy_manager._build_meta_payload(
        report, artifact, dataset_fp="fp-artifact", as_of_value="2025-02-01T00:00:00Z"
    )

    assert payload["node_id"] == "node-1"
    assert payload["coverage_bounds"] == [0, 120]
    assert payload["artifact"]["uri"] == "local://artifact"
    assert payload["world_id"] == "world-9"
    assert payload["execution_domain"] == "sim"


def test_build_world_payload_adds_strategy(strategy_manager):
    meta_payload = {
        "node_id": "node-1",
        "world_id": "world-9",
    }
    report = SimpleNamespace(world_id="world-9")

    payload = strategy_manager._build_world_payload(
        "strategy-123", report, meta_payload
    )

    assert payload["strategy_id"] == "strategy-123"
    assert payload["world_id"] == "world-9"
    assert payload["node_id"] == "node-1"
