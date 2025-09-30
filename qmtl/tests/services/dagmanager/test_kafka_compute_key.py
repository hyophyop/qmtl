from qmtl.foundation.common.compute_context import ComputeContext
from qmtl.foundation.common.compute_key import compute_compute_key
from qmtl.services.dagmanager.kafka_admin import compute_key


def test_compute_key_matches_common_helper() -> None:
    context = ComputeContext(world_id="world-x")
    expected = compute_compute_key("node-1", context)

    assert compute_key("node-1", world_id="world-x") == expected


def test_compute_key_ignores_dataset_fingerprint() -> None:
    base = compute_key("node-1", world_id="world-x", dataset_fingerprint="fp-a")
    changed = compute_key("node-1", world_id="world-x", dataset_fingerprint="fp-b")

    assert base == changed


def test_compute_key_falls_back_to_compute_only_domain() -> None:
    auto = compute_key("node-1", world_id="world-x")
    explicit = compute_key("node-1", world_id="world-x", execution_domain="backtest")

    assert auto == explicit
