from __future__ import annotations
import json
from pathlib import Path

import pandas as pd
import pytest

from qmtl.foundation.config import SeamlessConfig, UnifiedConfig
from qmtl.runtime.io.artifact import ArtifactRegistrar as IOArtifactRegistrar
from qmtl.runtime.sdk.artifacts import FileSystemArtifactRegistrar
from qmtl.runtime.sdk.configuration import runtime_config_override


def _make_config(**kwargs: object) -> UnifiedConfig:
    return UnifiedConfig(seamless=SeamlessConfig(**kwargs))


def test_from_config_disabled_by_default() -> None:
    with runtime_config_override(_make_config(artifacts_enabled=False)):
        assert FileSystemArtifactRegistrar.from_runtime_config() is None


def test_from_config_enabled_with_flag_and_dir(tmp_path) -> None:
    with runtime_config_override(
        _make_config(artifacts_enabled=True, artifact_dir=str(tmp_path))
    ):
        registrar = FileSystemArtifactRegistrar.from_runtime_config()

        assert isinstance(registrar, FileSystemArtifactRegistrar)
        assert registrar.base_dir == Path(tmp_path)


def test_from_config_alias_from_env(tmp_path) -> None:
    with runtime_config_override(
        _make_config(artifacts_enabled=True, artifact_dir=str(tmp_path))
    ):
        registrar = FileSystemArtifactRegistrar.from_env()

        assert isinstance(registrar, FileSystemArtifactRegistrar)
        assert registrar.base_dir == Path(tmp_path)


@pytest.mark.asyncio
async def test_filesystem_registrar_applies_partition_template(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "ts": [0, 60, 120, 180],
            "open": [1.0, 1.1, 1.2, 1.3],
            "high": [1.2, 1.3, 1.4, 1.5],
            "low": [0.9, 1.0, 1.1, 1.2],
            "close": [1.05, 1.15, 1.25, 1.35],
            "volume": [10, 11, 12, 13],
        }
    )

    registrar = FileSystemArtifactRegistrar(tmp_path, stabilization_bars=1)
    publication = await registrar.publish(
        frame,
        node_id="ohlcv:binance:BTC/USDT:1m",
        interval=60,
    )

    assert publication is not None
    manifest_path = Path(publication.manifest_uri)
    assert manifest_path.exists()

    expected_interval_dir = (
        Path(tmp_path)
        / "exchange=binance"
        / "symbol=BTC_USDT"
        / "timeframe=1m"
        / "60"
    )
    assert manifest_path.parent.parent == expected_interval_dir

    manifest = json.loads(manifest_path.read_text())
    assert manifest["producer"]["identity"] == "seamless@qmtl"
    assert manifest["producer"]["node_id"] == "ohlcv:binance:BTC/USDT:1m"
    assert manifest["conformance"]["flags"] == {}
    assert manifest["conformance"]["warnings"] == []
    assert manifest["as_of"].endswith("Z")


@pytest.mark.asyncio
async def test_filesystem_registrar_falls_back_for_unknown_node(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "ts": [0, 60, 120],
            "open": [1.0, 1.1, 1.2],
            "high": [1.0, 1.2, 1.3],
            "low": [0.9, 1.0, 1.1],
            "close": [1.0, 1.1, 1.2],
            "volume": [5, 6, 7],
        }
    )

    registrar = FileSystemArtifactRegistrar(tmp_path)
    publication = await registrar.publish(
        frame,
        node_id="custom-node",
        interval=60,
    )

    assert publication is not None
    manifest_path = Path(publication.manifest_uri)
    assert manifest_path.parent.parent == Path(tmp_path) / "custom-node" / "60"

    fingerprint_component = manifest_path.parent.name
    assert ":" not in fingerprint_component
    assert publication.dataset_fingerprint.replace(":", "-") == fingerprint_component


@pytest.mark.asyncio
async def test_io_registrar_includes_provenance_metadata() -> None:
    frame = pd.DataFrame(
        {
            "ts": [0, 60, 120],
            "open": [1.0, 1.1, 1.2],
            "high": [1.0, 1.2, 1.3],
            "low": [0.9, 1.0, 1.1],
            "close": [1.0, 1.1, 1.2],
            "volume": [5, 6, 7],
        }
    )

    registrar = IOArtifactRegistrar(stabilization_bars=1)
    publication = await registrar.publish(
        frame,
        node_id="custom-node",
        interval=60,
    )

    assert publication is not None
    manifest = publication.manifest
    assert manifest["producer"]["identity"] == "seamless@qmtl"
    assert manifest["producer"]["node_id"] == "custom-node"
    assert manifest["producer"]["interval"] == 60
    assert manifest["publication_watermark"].endswith("Z")
