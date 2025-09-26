from __future__ import annotations
from pathlib import Path

from qmtl.runtime.sdk.artifacts import FileSystemArtifactRegistrar


def test_from_env_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("QMTL_SEAMLESS_ARTIFACTS", raising=False)
    monkeypatch.delenv("QMTL_SEAMLESS_ARTIFACT_DIR", raising=False)

    assert FileSystemArtifactRegistrar.from_env() is None


def test_from_env_enabled_with_flag_and_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QMTL_SEAMLESS_ARTIFACTS", "1")
    monkeypatch.setenv("QMTL_SEAMLESS_ARTIFACT_DIR", str(tmp_path))

    registrar = FileSystemArtifactRegistrar.from_env()

    assert isinstance(registrar, FileSystemArtifactRegistrar)
    assert registrar.base_dir == Path(tmp_path)


def test_from_env_enabled_with_directory_only(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("QMTL_SEAMLESS_ARTIFACTS", raising=False)
    monkeypatch.setenv("QMTL_SEAMLESS_ARTIFACT_DIR", str(tmp_path))

    registrar = FileSystemArtifactRegistrar.from_env()

    assert isinstance(registrar, FileSystemArtifactRegistrar)
    assert registrar.base_dir == Path(tmp_path)
