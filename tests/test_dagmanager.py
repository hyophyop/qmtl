from qmtl.dagmanager import compute_node_id
from qmtl.dagmanager.neo4j_init import get_schema_queries
import hashlib


def test_compute_node_id_sha256():
    node_id = compute_node_id("type", "code", "cfg", "schema")
    expected = hashlib.sha256(b"type:code:cfg:schema").hexdigest()
    assert node_id == expected


def test_compute_node_id_sha3_fallback():
    data = ("A", "B", "C", "D")
    sha256_id = compute_node_id(*data)
    # same components would normally yield the same sha256, but the existing id
    # forces a fallback to sha3
    second_id = compute_node_id(*data, existing_ids={sha256_id})
    expected = hashlib.sha3_256(b"A:B:C:D").hexdigest()
    assert second_id == expected


def test_schema_queries():
    queries = get_schema_queries()
    assert "compute_pk" in queries[0]
    assert "queue_topic" in queries[1]
