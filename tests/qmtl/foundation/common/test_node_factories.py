from tests.qmtl.runtime.sdk.factories import (
    canonical_node_payload,
    indicator_node_payload,
    node_ids_crc32,
    tag_query_node_payload,
)


def test_factory_sorts_dependencies_for_hashing():
    first = canonical_node_payload(
        node_type="IndicatorNode",
        dependencies=["b", "a", "c"],
        config_hash="cfg-a",
    )
    second = canonical_node_payload(
        node_type="IndicatorNode",
        dependencies=["c", "b", "a"],
        config_hash="cfg-a",
    )
    assert first["dependencies"] == ["a", "b", "c"]
    assert first["node_id"] == second["node_id"]


def test_factory_canonicalises_params_nested_structures():
    node = indicator_node_payload(
        params={"tags": {"b", "a"}, "inner": {"z": 1, "a": 2}},
        config_hash="cfg-b",
    )
    assert node["params"]["tags"] == ["a", "b"]
    variant = indicator_node_payload(
        params={"inner": {"a": 2, "z": 1}, "tags": ["a", "b"]},
        config_hash="cfg-b",
    )
    assert node["node_id"] == variant["node_id"]


def test_node_ids_crc32_handles_iterables():
    tag = tag_query_node_payload(tags=["t"], config_hash="cfg-c")
    indicator = indicator_node_payload(config_hash="cfg-d")
    checksum = node_ids_crc32([tag, indicator])
    assert checksum == node_ids_crc32((tag, indicator))
