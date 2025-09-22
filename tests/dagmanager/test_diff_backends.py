from __future__ import annotations

import pytest

from qmtl.dagmanager.diff_service import (
    DiffService,
    KafkaQueueManager,
    Neo4jNodeRepository,
    NodeRecord,
)
from qmtl.dagmanager.kafka_admin import KafkaAdmin
from qmtl.dagmanager.node_repository import MemoryNodeRepository
from qmtl.dagmanager.topic import topic_name

from .diff_fakes import FakeAdmin, FakeDriver, FakeQueue, FakeStream
from .diff_helpers import dag_node, make_diff_request, partition_with_context

pytestmark = [
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore:unclosed <socket.socket[^>]*>"),
    pytest.mark.filterwarnings("ignore:unclosed event loop"),
]


def test_integration_with_backends():
    records = [
        {
            "node_id": "A",
            "code_hash": "c1",
            "schema_hash": "s1",
            "topic": topic_name("asset", "N", "c1", "v1"),
        }
    ]
    driver = FakeDriver(records)
    admin = FakeAdmin()
    stream = FakeStream()
    repo = Neo4jNodeRepository(driver)
    queue_manager = KafkaQueueManager(KafkaAdmin(admin))
    service = DiffService(repo, queue_manager, stream)

    request = make_diff_request(
        strategy_id="sid",
        nodes=[
            dag_node("A", code_hash="c1", schema_hash="s1"),
            dag_node("B", code_hash="c2", schema_hash="s2"),
        ]
    )

    chunk = service.diff(request)

    expected_a = topic_name("asset", "N", "c1", "v1")
    expected_b = topic_name("asset", "N", "c2", "v1")

    assert chunk.queue_map == {
        partition_with_context("A", None, None): expected_a,
        partition_with_context("B", None, None): expected_b,
    }
    assert any("sid" in params for _, params in driver.session_obj.run_calls)
    assert admin.created and admin.created[0][0] == expected_b
    assert stream.chunks[0] == chunk


def test_integration_with_memory_repo(tmp_path):
    path = tmp_path / "mem.gpickle"
    repo = MemoryNodeRepository(str(path))
    repo.add_node(
        NodeRecord(
            "A",
            "N",
            "c1",
            "s1",
            "id1",
            None,
            None,
            [],
            None,
            False,
            topic_name("asset", "N", "c1", "v1"),
        )
    )

    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    request = make_diff_request(
        nodes=[
            dag_node("A", code_hash="c1", schema_hash="s1"),
            dag_node("B", code_hash="c2", schema_hash="s2"),
        ]
    )

    chunk = service.diff(request)

    expected_a = topic_name("asset", "N", "c1", "v1")
    expected_b = topic_name("asset", "N", "c2", "v1")

    assert chunk.queue_map == {
        partition_with_context("A", None, None): expected_a,
        partition_with_context("B", None, None): expected_b,
    }

    repo2 = MemoryNodeRepository(str(path))
    assert "A" in repo2.get_nodes(["A"])
