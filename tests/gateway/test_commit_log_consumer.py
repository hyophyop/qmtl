from qmtl.gateway.commit_log_consumer import CommitLogDeduplicator
from qmtl.gateway import metrics


def test_commit_log_deduplicator_filters_duplicates():
    metrics.reset_metrics()
    dedup = CommitLogDeduplicator()
    records = [
        ("n1", 100, "h1", {"a": 1}),
        ("n1", 100, "h1", {"a": 2}),  # duplicate
        ("n1", 100, "h2", {"a": 3}),
    ]
    out = list(dedup.filter(records))
    assert out == [
        ("n1", 100, "h1", {"a": 1}),
        ("n1", 100, "h2", {"a": 3}),
    ]
    # second batch should drop already seen key
    more = list(dedup.filter([( "n1", 100, "h1", {"a": 4})]))
    assert more == []
    assert metrics.commit_duplicate_total._value.get() == 2
