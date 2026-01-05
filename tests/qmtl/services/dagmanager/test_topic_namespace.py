from __future__ import annotations

from qmtl.services.dagmanager.topic import (
    build_namespace,
    ensure_namespace,
    normalize_namespace,
    topic_name,
)


def test_build_namespace_sanitizes_world_and_domain() -> None:
    assert build_namespace("World 1", "Live/Prod") == "world-1.live-prod"


def test_ensure_namespace_prefixes_topic_once() -> None:
    base = "asset_indicator_abcdef_v1"
    prefixed = ensure_namespace(base, {"world_id": "World-1", "execution_domain": "Live"})
    assert prefixed == "world-1.live.asset_indicator_abcdef_v1"

    # Idempotent when already prefixed
    again = ensure_namespace(prefixed, "world-1.live")
    assert again == prefixed


def test_topic_name_applies_namespace_prefix() -> None:
    topic = topic_name(
        "asset",
        "node",
        "blake3:abcdef123456",
        "v1",
        namespace={"world_id": "World-1", "execution_domain": "DryRun"},
    )
    assert topic.startswith("world-1.dryrun.")
    assert topic.endswith("asset_node_abcdef12_v1")


def test_normalize_namespace_accepts_mapping_input() -> None:
    normalized = normalize_namespace({"world": "W-1", "domain": "Live"})
    assert normalized == "w-1.live"
