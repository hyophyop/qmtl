from pathlib import Path

import pytest

from qmtl.foundation.config import CacheConfig, UnifiedConfig
from qmtl.runtime.sdk import Strategy, StreamInput, ProcessingNode, configuration
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.feature_store import FeatureArtifactPlane, FileSystemFeatureStore


class _ArtifactStrategy(Strategy):
    def __init__(self, *, multiplier: float) -> None:
        super().__init__()
        self.multiplier = multiplier
        self.src = None
        self.factor = None
        self.outputs: list[dict] = []

    def setup(self) -> None:
        self.src = StreamInput(interval=1, period=1)

        def _compute(view):
            series = view[self.src][self.src.interval]
            if not series:
                return None
            ts, payload = series[-1]
            artifacts = view.feature_artifacts(self.factor, instrument=payload["instrument"])
            if artifacts:
                value = artifacts[-1][1]
            else:
                value = {
                    "instrument": payload["instrument"],
                    "value": payload["value"] * self.multiplier,
                }
            self.outputs.append(value)
            return value

        self.factor = ProcessingNode(
            input=self.src,
            compute_fn=_compute,
            name="factor",
            interval=1,
            period=1,
        )
        self.factor.enable_feature_artifacts = True
        self.add_nodes([self.src, self.factor])


@pytest.fixture
def artifact_plane(tmp_path: Path):
    base = tmp_path / "artifacts"
    plane = FeatureArtifactPlane(FileSystemFeatureStore(base))
    prev = Runner.feature_artifact_plane()
    Runner.set_feature_artifact_plane(plane)
    try:
        yield plane
    finally:
        Runner.set_feature_artifact_plane(prev)

def test_feature_artifacts_written_and_read(artifact_plane):
    strategy = _ArtifactStrategy(multiplier=2.0)
    strategy.setup()
    strategy.factor.dataset_fingerprint = "lake:blake3:test"
    strategy.factor.execution_domain = "backtest"
    artifact_plane.configure(dataset_fingerprint="lake:blake3:test", execution_domain="backtest")

    Runner.feed_queue_data(
        strategy.src,
        strategy.src.node_id,
        strategy.src.interval,
        1,
        {"instrument": "BTC", "value": 10},
    )
    result = Runner.feed_queue_data(
        strategy.factor,
        strategy.src.node_id,
        strategy.src.interval,
        1,
        {"instrument": "BTC", "value": 10},
    )
    assert result["value"] == 20
    assert artifact_plane.count(strategy.factor, instrument="BTC") == 1
    series = artifact_plane.load_series(strategy.factor, instrument="BTC")
    assert series[-1][1]["value"] == 20


def test_runner_reuses_artifacts_across_domains(tmp_path: Path):
    cfg = UnifiedConfig(
        cache=CacheConfig(
            feature_artifacts_enabled=True,
            feature_artifact_dir=str(tmp_path / "plane"),
        ),
        present_sections=frozenset({"cache"}),
    )
    with configuration.runtime_config_override(cfg):
        plane = FeatureArtifactPlane.from_config()
    assert plane is not None
    previous = Runner.feature_artifact_plane()
    Runner.set_feature_artifact_plane(plane)

    backtest = _ArtifactStrategy(multiplier=2.0)
    backtest.setup()
    backtest.factor.dataset_fingerprint = "lake:blake3:data"
    backtest.factor.execution_domain = "backtest"
    plane.configure(dataset_fingerprint="lake:blake3:data", execution_domain="backtest")

    Runner.feed_queue_data(
        backtest.src,
        backtest.src.node_id,
        backtest.src.interval,
        1,
        {"instrument": "ETH", "value": 5},
    )
    result = Runner.feed_queue_data(
        backtest.factor,
        backtest.src.node_id,
        backtest.src.interval,
        1,
        {"instrument": "ETH", "value": 5},
    )
    assert result["value"] == 10
    assert plane.count(backtest.factor, instrument="ETH") == 1

    live = _ArtifactStrategy(multiplier=4.0)
    live.setup()
    live.factor.dataset_fingerprint = "lake:blake3:data"
    live.factor.execution_domain = "live"
    plane.configure(dataset_fingerprint="lake:blake3:data", execution_domain="live")

    Runner.feed_queue_data(
        live.src,
        live.src.node_id,
        live.src.interval,
        1,
        {"instrument": "ETH", "value": 5},
    )
    live_result = Runner.feed_queue_data(
        live.factor,
        live.src.node_id,
        live.src.interval,
        1,
        {"instrument": "ETH", "value": 5},
    )
    assert live_result["value"] == 10
    assert plane.count(live.factor, instrument="ETH") == 1
    assert live.factor.cache._active_execution_domain == "live"
    assert backtest.factor.cache._active_execution_domain == "backtest"

    Runner.set_feature_artifact_plane(previous)


def test_live_domain_does_not_write_feature_artifacts(artifact_plane):
    strategy = _ArtifactStrategy(multiplier=3.0)
    strategy.setup()
    strategy.factor.dataset_fingerprint = "lake:blake3:live-test"
    strategy.factor.execution_domain = "live"
    artifact_plane.configure(
        dataset_fingerprint="lake:blake3:live-test",
        execution_domain="live",
    )

    initial_count = artifact_plane.count(strategy.factor, instrument="BTC")

    Runner.feed_queue_data(
        strategy.src,
        strategy.src.node_id,
        strategy.src.interval,
        1,
        {"instrument": "BTC", "value": 10},
    )
    result = Runner.feed_queue_data(
        strategy.factor,
        strategy.src.node_id,
        strategy.src.interval,
        1,
        {"instrument": "BTC", "value": 10},
    )

    assert result["value"] == 30
    assert artifact_plane.count(strategy.factor, instrument="BTC") == initial_count


def test_from_env_preserves_environment_overrides(monkeypatch, tmp_path):
    configuration.reset_runtime_config_cache()
    base_dir = tmp_path / "env-plane"

    monkeypatch.setenv("QMTL_FEATURE_ARTIFACTS", "1")
    monkeypatch.setenv("QMTL_FEATURE_ARTIFACT_DIR", str(base_dir))
    monkeypatch.setenv("QMTL_FEATURE_ARTIFACT_VERSIONS", "3")
    monkeypatch.setenv("QMTL_FEATURE_ARTIFACT_WRITE_DOMAINS", "backtest paper")

    with pytest.deprecated_call():
        plane = FeatureArtifactPlane.from_env()

    assert plane is not None
    assert plane.backend.base_dir == base_dir
    assert plane.backend.max_versions == 3
    assert plane.write_domains == {"backtest", "paper"}


def test_from_env_overrides_yaml_configuration(monkeypatch, tmp_path):
    cfg = UnifiedConfig(
        cache=CacheConfig(
            feature_artifacts_enabled=False,
            feature_artifact_dir=str(tmp_path / "yaml"),
            feature_artifact_write_domains=["dryrun"],
        ),
        present_sections=frozenset({"cache"}),
    )

    base_dir = tmp_path / "env-plane"
    monkeypatch.setenv("QMTL_FEATURE_ARTIFACTS", "true")
    monkeypatch.setenv("QMTL_FEATURE_ARTIFACT_DIR", str(base_dir))
    monkeypatch.setenv("QMTL_FEATURE_ARTIFACT_WRITE_DOMAINS", "live,backtest")

    with configuration.runtime_config_override(cfg):
        with pytest.deprecated_call():
            plane = FeatureArtifactPlane.from_env()

    assert plane is not None
    assert plane.backend.base_dir == base_dir
    assert plane.write_domains == {"live", "backtest"}
