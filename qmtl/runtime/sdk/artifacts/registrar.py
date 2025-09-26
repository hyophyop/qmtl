"""Artifact registrar implementations for Seamless providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, MutableMapping, Protocol

import pandas as pd

from qmtl.runtime.io.artifact import (
    ArtifactRegistrar as _IOArtifactRegistrar,
    ArtifactPublication,
)


@dataclass(slots=True)
class ProducerContext:
    """Context information recorded in manifests for provenance."""

    node_id: str
    interval: int
    world_id: str
    strategy_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "interval": int(self.interval),
            "world_id": self.world_id,
        }
        if self.strategy_id:
            payload["strategy_id"] = self.strategy_id
        return payload


class ArtifactRegistrar(Protocol):
    """Protocol for registrars accepted by ``SeamlessDataProvider``."""

    def publish(
        self,
        frame: pd.DataFrame,
        *,
        node_id: str,
        interval: int,
        conformance_report: Any | None = None,
        requested_range: tuple[int, int] | None = None,
    ) -> ArtifactPublication | None | Any:
        """Publish ``frame`` and return publication metadata.

        Implementations may return a coroutine that resolves to an
        ``ArtifactPublication``. ``SeamlessDataProvider`` will await the result
        when necessary.
        """


def _sanitize_component(text: str) -> str:
    cleaned = text.replace("/", "_").replace("..", "")
    cleaned = cleaned.replace(":", "-")
    return cleaned or "__"


class FileSystemArtifactRegistrar(_IOArtifactRegistrar):
    """Persist artifacts to the local filesystem for testing and development."""

    def __init__(
        self,
        base_dir: str | os.PathLike[str],
        *,
        stabilization_bars: int = 0,
        conformance_version: str = "v2",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(
            store=self._store,
            stabilization_bars=stabilization_bars,
            conformance_version=conformance_version,
        )

    @classmethod
    def from_env(cls) -> "FileSystemArtifactRegistrar | None":
        """Create a registrar from environment configuration.

        Registrars are opt-in so that optional parquet dependencies are not
        required for every seamless fetch. A registrar will only be created
        when ``QMTL_SEAMLESS_ARTIFACTS`` is explicitly enabled or when a
        custom artifact directory is provided.
        """

        flag = os.getenv("QMTL_SEAMLESS_ARTIFACTS")
        dir_override = os.getenv("QMTL_SEAMLESS_ARTIFACT_DIR")

        if flag is None and not dir_override:
            return None

        normalized = str(flag or "").strip().lower()
        if normalized in {"0", "false", "off", "no"}:
            return None

        base = dir_override or ".qmtl_seamless_artifacts"
        return cls(base)

    # ------------------------------------------------------------------
    def _target_dir(self, manifest: MutableMapping[str, Any]) -> Path:
        node_part = _sanitize_component(str(manifest.get("node_id", "unknown")))
        interval_part = _sanitize_component(str(manifest.get("interval", "0")))
        fingerprint_part = _sanitize_component(str(manifest.get("dataset_fingerprint", "fp")))
        return self.base_dir / node_part / interval_part / fingerprint_part

    def _write_manifest(self, path: Path, manifest: MutableMapping[str, Any]) -> None:
        path.write_text(json.dumps(manifest, sort_keys=True))

    def _store(self, frame: pd.DataFrame, manifest: MutableMapping[str, Any]) -> str:
        target = self._target_dir(manifest)
        target.mkdir(parents=True, exist_ok=True)

        data_path = target / "data.parquet"
        try:
            frame.to_parquet(data_path)
        except (ImportError, ValueError):  # pragma: no cover - exercised in environments w/o parquet
            data_path = target / "data.json"
            data_path.write_text(frame.to_json(orient="records"))

        manifest_path = target / "manifest.json"
        watermark = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        manifest["publication_watermark"] = watermark
        start, end = manifest.get("range", [None, None])
        if start is not None and end is not None:
            manifest["coverage"] = {"start": int(start), "end": int(end)}

        dataset_fp = str(manifest.get("dataset_fingerprint", ""))
        if dataset_fp.startswith("lake:sha256:"):
            manifest["dataset_fingerprint"] = dataset_fp.replace("lake:", "", 1)

        producer = ProducerContext(
            node_id=str(manifest.get("node_id", "unknown")),
            interval=int(manifest.get("interval", 0)),
            world_id=os.getenv("WORLD_ID", "default"),
            strategy_id=os.getenv("QMTL_STRATEGY_ID"),
        )
        manifest["producer"] = producer.as_dict()
        manifest["storage"] = {
            "data_uri": str(data_path),
            "manifest_uri": str(manifest_path),
        }
        manifest["manifest_uri"] = str(manifest_path)

        self._write_manifest(manifest_path, manifest)
        return str(data_path)


__all__ = [
    "ArtifactPublication",
    "ArtifactRegistrar",
    "FileSystemArtifactRegistrar",
]
