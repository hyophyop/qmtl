import logging

from qmtl.sdk import TagQueryNode, MatchMode


def test_update_queues_warmup_and_drop():
    node = TagQueryNode(["t"], interval="60s", period=2)
    node.update_queues(["q1"])
    node.pre_warmup = False
    node.cache.append("q1", 60, 60, {"v": 1})

    node.update_queues(["q1", "q2"])
    assert node.pre_warmup
    assert set(node.upstreams) == {"q1", "q2"}

    node.pre_warmup = False
    node.cache.append("q2", 60, 120, {"v": 2})
    node.update_queues(["q2"])
    assert node.cache.get_slice("q1", 60, count=1) == []
    assert node.upstreams == ["q2"]


def test_update_queues_logs_warning_when_empty(caplog):
    node = TagQueryNode(["t"], interval="60s", period=1)
    node.update_queues(["q1"])
    with caplog.at_level(logging.WARNING):
        node.update_queues([])
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_tag_query_node_accepts_string_match_mode():
    node = TagQueryNode(["t"], interval="60s", period=1, match_mode="all")
    assert node.match_mode is MatchMode.ALL
