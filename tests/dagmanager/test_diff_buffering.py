from __future__ import annotations

import pytest

from qmtl.dagmanager.diff_service import NodeRecord
from qmtl.dagmanager.topic import topic_name

from .diff_helpers import dag_node, make_diff_request, partition_with_context

pytestmark = [
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore:unclosed <socket.socket[^>]*>"),
    pytest.mark.filterwarnings("ignore:unclosed event loop"),
]


def test_schema_change_buffering_flag(diff_service, fake_repo, fake_queue):
    fake_repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "old",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c1", "v1"),
    )

    request = make_diff_request(
        nodes=[
            dag_node(
                "A",
                code_hash="c1",
                schema_hash="new",
                period=3,
            ),
        ]
    )

    chunk = diff_service.diff(request)

    expected_a = topic_name("asset", "N", "c1", "v1")

    assert chunk.queue_map[partition_with_context("A", None, None)] == expected_a
    assert not chunk.new_nodes
    assert fake_queue.calls == []
    assert [n.node_id for n in chunk.buffering_nodes] == ["A"]
    assert chunk.buffering_nodes[0].lag == 3
