from blake3 import blake3
import hashlib

from qmtl.dagmanager import compute_node_id
from qmtl.common.nodespec import serialize_nodespec
from qmtl.dagmanager.neo4j_init import get_schema_queries


def test_compute_node_id_blake3():
    spec = {
        "node_type": "type",
        "interval": 5,
        "period": 1,
        "params": {"alpha": 1, "beta": 2},
        "dependencies": ["dep-b", "dep-a"],
        "schema_compat_id": "schema-major",
        "code_hash": "code",
    }
    node_id = compute_node_id(spec)
    expected = blake3(serialize_nodespec(spec)).hexdigest()
    assert node_id == f"blake3:{expected}"


def test_compute_node_id_collision():
    data = {
        "node_type": "A",
        "interval": 1,
        "period": 1,
        "params": {"foo": 1},
        "dependencies": ["dep-1"],
        "schema_compat_id": "schema-major",
        "code_hash": "B",
    }
    first = compute_node_id(data)
    second = compute_node_id(data, existing_ids={first})
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
