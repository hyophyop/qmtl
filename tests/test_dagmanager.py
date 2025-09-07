from blake3 import blake3
import hashlib

from qmtl.dagmanager import compute_node_id
from qmtl.common import compute_legacy_node_id
from qmtl.dagmanager.neo4j_init import get_schema_queries


def test_compute_node_id_blake3():
    node_id = compute_node_id("type", "code", "cfg", "schema")
    expected = blake3(b"type:code:cfg:schema").hexdigest()
    assert node_id == f"blake3:{expected}"


def test_compute_node_id_collision():
    data = ("A", "B", "C", "D")
    first = compute_node_id(*data)
    second = compute_node_id(*data, existing_ids={first})
    assert first != second
    assert second.startswith("blake3:")


def test_compute_legacy_node_id_sha256():
    node_id = compute_legacy_node_id("type", "code", "cfg", "schema", "w1")
    expected = hashlib.sha256(b"w1:type:code:cfg:schema").hexdigest()
    assert node_id == expected


def test_schema_queries():
    queries = get_schema_queries()
    assert "compute_pk" in queries[0]
    assert "kafka_topic" in queries[1]
