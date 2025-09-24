from qmtl.services.dagmanager.neo4j_init import get_schema_queries, get_drop_queries


def test_get_drop_queries_covers_all_created_objects():
    create = get_schema_queries()
    drop = get_drop_queries()

    # Extract names from create statements (last token before IF/ON clause varies)
    # We rely on explicit names used in SCHEMA_QUERIES.
    expected_names = {
        "compute_pk",
        "kafka_topic",
        "compute_tags",
        "queue_interval",
        "compute_buffering_since",
    }

    # Validate create statements reference the expected names
    assert all(any(name in stmt for stmt in create) for name in expected_names)

    # Validate drop statements contain all expected names with IF EXISTS guard
    for name in expected_names:
        assert any(stmt.endswith("IF EXISTS") and name in stmt for stmt in drop), name

    # No duplicates in drop statements
    assert len(drop) == len(set(drop))

