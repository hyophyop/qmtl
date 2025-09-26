"""Artifact registrar implementations for Seamless providers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Protocol, Sequence, Tuple
import time

import pandas as pd


@dataclass(slots=True)
class ArtifactPublication:
    """Details about a published artifact manifest."""

    dataset_fingerprint: str
    as_of: int
    coverage_bounds: tuple[int, int]
    manifest_uri: str
    data_uri: str | None = None


class ArtifactRegistrar(Protocol):
    """Publish stabilized frames into an artifact catalog."""

    def publish(
        self,
        frame: pd.DataFrame,
        *,
        node_id: str,
        interval: int,
        coverage_bounds: tuple[int, int],
        fingerprint: str,
        as_of: int,
        conformance_flags: dict[str, int] | None = None,
        conformance_warnings: Sequence[str] | None = None,
        request_window: tuple[int, int] | None = None,
    ) -> ArtifactPublication:
        """Persist ``frame`` and return publication details."""


def _sanitize_component(text: str) -> str:
    cleaned = text.replace("/", "_").replace("..", "")
    cleaned = cleaned.replace(":", "-")
    return cleaned or "__"


class FileSystemArtifactRegistrar:
    """Persist artifacts to the local filesystem for testing and development."""

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

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

    def _target_dir(self, node_id: str, interval: int, fingerprint: str) -> Path:
        node_part = _sanitize_component(node_id)
        fp_part = _sanitize_component(fingerprint)
        return self.base_dir / node_part / str(interval) / fp_part

    def publish(
        self,
        frame: pd.DataFrame,
        *,
        node_id: str,
        interval: int,
        coverage_bounds: Tuple[int, int],
        fingerprint: str,
        as_of: int,
        conformance_flags: dict[str, int] | None = None,
        conformance_warnings: Sequence[str] | None = None,
        request_window: tuple[int, int] | None = None,
    ) -> ArtifactPublication:
        target = self._target_dir(node_id, interval, fingerprint)
        target.mkdir(parents=True, exist_ok=True)

        data_path = target / "data.parquet"
        frame.to_parquet(data_path)

        manifest_path = target / "manifest.json"
        payload = {
            "dataset_fingerprint": fingerprint,
            "as_of": int(as_of),
            "node_id": node_id,
            "interval": int(interval),
            "coverage_bounds": [int(coverage_bounds[0]), int(coverage_bounds[1])],
            "rows": int(len(frame)),
            "conformance_flags": dict(conformance_flags or {}),
            "conformance_warnings": list(conformance_warnings or ()),
            "request_window": list(request_window or ()),
            "published_at": int(time.time()),
        }
        manifest_path.write_text(json.dumps(payload, sort_keys=True))

        return ArtifactPublication(
            dataset_fingerprint=fingerprint,
            as_of=int(as_of),
            coverage_bounds=(int(coverage_bounds[0]), int(coverage_bounds[1])),
            manifest_uri=str(manifest_path),
            data_uri=str(data_path),
        )


__all__ = [
    "ArtifactPublication",
    "ArtifactRegistrar",
    "FileSystemArtifactRegistrar",
]

