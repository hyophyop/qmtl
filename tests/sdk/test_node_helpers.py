from __future__ import annotations

from qmtl.sdk import hash_utils, node_validation
from qmtl.sdk.nodes.config import NodeConfig
from qmtl.sdk.nodes.mixins import LateEventPolicy


def _dummy_compute(view) -> None:  # pragma: no cover - simple stub
    return None


def test_node_config_builds_with_validator() -> None:
    config = NodeConfig.build(
        input=None,
        compute_fn=_dummy_compute,
        name="example",
        tags=["t1"],
        interval="60s",
        period=5,
        config={"enable_feature_artifacts": True},
        schema={"schema_compat_id": "compat"},
        expected_schema={},
        allowed_lateness=3,
        on_late="ignore",
        runtime_compat="loose",
        validator=node_validation,
        hash_utils=hash_utils,
    )

    assert config.interval == 60
    assert config.period == 5
    assert config.tags == ["t1"]
    assert config.enable_feature_artifacts is True
    assert config.schema_compat_id == "compat"
    assert config.allowed_lateness == 3
    assert config.on_late == "ignore"
    assert config.inputs == []


def test_node_config_schema_fallback_to_hash() -> None:
    config = NodeConfig.build(
        input=None,
        compute_fn=_dummy_compute,
        name="example",
        tags=None,
        interval=60,
        period=1,
        config=None,
        schema={},
        expected_schema={},
        allowed_lateness=0,
        on_late="recompute",
        runtime_compat="loose",
        validator=node_validation,
        hash_utils=hash_utils,
    )

    assert config.schema_compat_id == hash_utils.schema_hash({})


def test_late_event_policy_behaviour() -> None:
    sink: list[tuple[str, int, object]] = []
    policy = LateEventPolicy("side_output", sink)

    assert policy.should_process("up", 30, 20, object()) is True
    late_payload = object()
    assert (
        policy.should_process("up", 10, 20, late_payload) is False
    )  # late event captured
    assert sink == [("up", 10, late_payload)]

    ignore_policy = LateEventPolicy("ignore", sink)
    assert ignore_policy.should_process("up", 5, 20, None) is False

