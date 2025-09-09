from blake3 import blake3
import hashlib

from qmtl.dagmanager import compute_node_id
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


def test_no_legacy_nodeid_helper_present():
    # Legacy helper has been removed; ensure import path no longer exposes it
    import qmtl.common as common
    assert not hasattr(common, "compute_legacy_node_id")


def test_schema_queries():
    queries = get_schema_queries()
    assert "compute_pk" in queries[0]
    assert "kafka_topic" in queries[1]
