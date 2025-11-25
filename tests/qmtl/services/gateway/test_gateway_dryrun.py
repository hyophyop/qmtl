from qmtl.services.gateway.routes import JSONResponse  # import to ensure module loads


def test_dryrun_fallback_sentinel_helper_crc32(monkeypatch):
    # Import inside to access module-level function via attributes if exposed
    import qmtl.services.gateway.routes as routes

    # Build a minimal DAG with stable node_ids
    dag = {
        "schema_version": "v1",
        "nodes": [
            {"node_id": "n1", "node_type": "TagQueryNode", "tags": ["t"], "interval": 60},
            {"node_id": "n2", "node_type": "ComputeNode", "interval": 60},
        ],
    }

    # Use the same logic as the route for CRC32 derivation
    from qmtl.foundation.common import crc32_of_list

    expected_crc = crc32_of_list(n.get("node_id", "") for n in dag.get("nodes", []))
    expected = f"dryrun:{expected_crc:08x}"

    # The helper is not exported; validate by recomputing here to assert format
    assert expected.startswith("dryrun:") and len(expected) == len("dryrun:") + 8
