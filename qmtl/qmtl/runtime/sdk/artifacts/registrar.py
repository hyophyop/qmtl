"""Artifact registrar implementations for Seamless providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, MutableMapping, Protocol

import pandas as pd

from qmtl.foundation.config import SeamlessConfig
from qmtl.runtime.io.artifact import (
    ArtifactRegistrar as _IOArtifactRegistrar,
    ArtifactPublication,
)
from qmtl.runtime.sdk.configuration import get_seamless_config

from .. import configuration


def _resolve_strategy_id() -> str | None:
    try:
        cfg = configuration.get_connectors_config()
        value = getattr(cfg, "strategy_id", None)
    except Exception:  # pragma: no cover - defensive cache access
        value = None

    if value:
        text = str(value).strip()
        if text:
            return text

    raw = os.getenv("QMTL_STRATEGY_ID")
    if raw:
        text = raw.strip()
        if text:
            return text
    return None


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
        publish_fingerprint: bool = True,
        early_fingerprint: bool = False,
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
        partition_template: str = "exchange={exchange}/symbol={symbol}/timeframe={timeframe}",
        producer: str | None = "seamless@qmtl",
    ) -> None:
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._partition_template = partition_template
        self._producer_identity = producer or None
        super().__init__(
            store=self._store,
            stabilization_bars=stabilization_bars,
            conformance_version=conformance_version,
            producer_identity=producer,
        )

    @classmethod
    def from_runtime_config(
        cls, config: SeamlessConfig | None = None
    ) -> "FileSystemArtifactRegistrar | None":
        """Create a registrar when artifacts are enabled in configuration."""

        cfg = config or get_seamless_config()
        if not bool(cfg.artifacts_enabled):
            return None

        base = cfg.artifact_dir or ".qmtl_seamless_artifacts"
        return cls(base)

    @classmethod
    def from_env(cls) -> "FileSystemArtifactRegistrar | None":
        """Backward-compatible alias for :meth:`from_runtime_config`."""

        return cls.from_runtime_config()

    # ------------------------------------------------------------------
    def _target_dir(self, manifest: MutableMapping[str, Any]) -> Path:
        node_id = str(manifest.get("node_id", "unknown"))
        node_part = _sanitize_component(node_id)
        interval_part = _sanitize_component(str(manifest.get("interval", "0")))
        fingerprint_part = _sanitize_component(str(manifest.get("dataset_fingerprint", "fp")))

        partitioned = self._partition_components(node_id)
        if partitioned is None:
            return self.base_dir / node_part / interval_part / fingerprint_part

        target = self.base_dir
        for component in partitioned:
            target /= component
        target /= interval_part
        return target / fingerprint_part

    def _partition_components(self, node_id: str) -> list[str] | None:
        from qmtl.runtime.sdk.ohlcv_nodeid import parse as parse_ohlcv_node_id

        template = self._partition_template
        if not template:
            return None

        parsed = parse_ohlcv_node_id(node_id)
        if not parsed:
            return None

        exchange, symbol, timeframe = parsed
        replacements = {
            "exchange": _sanitize_component(exchange),
            "symbol": _sanitize_component(symbol),
            "timeframe": _sanitize_component(timeframe),
            "node_id": _sanitize_component(node_id),
        }

        try:
            rendered = template.format(**replacements)
        except KeyError:
            return None

        components = [part for part in rendered.split("/") if part]
        if not components:
            return None
        return [_sanitize_component(part) for part in components]

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

        as_of = manifest.get("as_of")
        if isinstance(as_of, datetime):
            manifest["as_of"] = as_of.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        elif as_of is not None:
            manifest["as_of"] = str(as_of)

        manifest.setdefault("stabilization_bars", self.stabilization_bars)
        manifest.setdefault("conformance_version", self.conformance_version)
        if "conformance" not in manifest:
            manifest["conformance"] = {"flags": {}, "warnings": []}
        else:
            manifest["conformance"] = {
                "flags": dict(manifest["conformance"].get("flags", {})),
                "warnings": list(manifest["conformance"].get("warnings", [])),
            }

        producer = ProducerContext(
            node_id=str(manifest.get("node_id", "unknown")),
            interval=int(manifest.get("interval", 0)),
            world_id=os.getenv("WORLD_ID", "default"),
            strategy_id=_resolve_strategy_id(),
        )
        producer_payload = producer.as_dict()
        if self._producer_identity:
            producer_payload["identity"] = self._producer_identity
        manifest["producer"] = producer_payload
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
