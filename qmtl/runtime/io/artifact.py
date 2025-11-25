from __future__ import annotations

"""Helpers for publishing stabilized Seamless artifacts."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import logging
from typing import Any, Awaitable, Callable, MutableMapping, Sequence

import pandas as pd

from qmtl.runtime.sdk.conformance import ConformanceReport

logger = logging.getLogger(__name__)

ArtifactStore = Callable[[pd.DataFrame, MutableMapping[str, Any]], Awaitable[str | None] | str | None]


@dataclass(slots=True)
class ArtifactPublication:
    """Metadata describing a stabilized artifact publication."""

    dataset_fingerprint: str
    as_of: str
    node_id: str
    start: int
    end: int
    rows: int
    uri: str | None = None
    manifest_uri: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _FrameStats:
    """Computed metadata about a stabilized frame."""

    start: int
    end: int
    rows: int
    as_of: str


class ArtifactRegistrar:
    """Compute dataset fingerprints and optionally persist stabilized artifacts."""

    _PREFERRED_COLUMNS: Sequence[str] = ("ts", "open", "high", "low", "close", "volume")

    def __init__(
        self,
        *,
        store: ArtifactStore | None = None,
        stabilization_bars: int = 2,
        conformance_version: str = "v2",
        float_format: str = "%.10f",
        producer_identity: str | None = "seamless@qmtl",
    ) -> None:
        if stabilization_bars < 0:
            raise ValueError("stabilization_bars must be >= 0")
        self._store = store
        self._stabilization_bars = int(stabilization_bars)
        self._conformance_version = str(conformance_version)
        self._float_format = float_format
        identity = (producer_identity or "").strip()
        self._producer_identity = identity or "seamless@qmtl"

    @property
    def stabilization_bars(self) -> int:
        return self._stabilization_bars

    @property
    def conformance_version(self) -> str:
        return self._conformance_version

    async def publish(
        self,
        frame: pd.DataFrame,
        *,
        node_id: str,
        interval: int,
        conformance_report: ConformanceReport | None = None,
        requested_range: tuple[int, int] | None = None,
        publish_fingerprint: bool = True,
        early_fingerprint: bool = False,
    ) -> ArtifactPublication | None:
        """Stabilize ``frame`` and return publication metadata.

        When ``store`` was supplied at construction time the stabilized frame and
        manifest metadata are handed to it. Failures during persistence are
        logged and do not raise.
        """

        if not self._should_publish(frame, publish_fingerprint):
            return None

        stabilized = self._stabilize_frame(self._canonicalize_frame(frame))
        if stabilized.empty:
            return None

        stats = self._frame_stats(stabilized)
        fingerprint = self._compute_fingerprint(
            stabilized=stabilized,
            node_id=node_id,
            interval=interval,
            start=stats.start,
            end=stats.end,
        )
        manifest = self._build_manifest(
            node_id=node_id,
            interval=interval,
            stats=stats,
            fingerprint=fingerprint,
            requested_range=requested_range,
            conformance_report=conformance_report,
        )
        uri = await self._store_artifact(stabilized, manifest, node_id=node_id)

        return self._build_publication(
            fingerprint=fingerprint,
            stats=stats,
            node_id=node_id,
            uri=uri,
            manifest=manifest,
        )

    # ------------------------------------------------------------------
    def _canonicalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        working = frame.copy(deep=True)
        if "ts" in working.columns:
            working["ts"] = pd.to_numeric(working["ts"], errors="coerce").astype("Int64")
            working.dropna(subset=["ts"], inplace=True)
            working["ts"] = working["ts"].astype("int64")
            working.sort_values("ts", inplace=True)
            working.reset_index(drop=True, inplace=True)

        preferred = [col for col in self._PREFERRED_COLUMNS if col in working.columns]
        extras = [col for col in working.columns if col not in preferred]
        ordered = preferred + extras
        working = working.loc[:, ordered]

        for col in ("open", "high", "low", "close", "volume"):
            if col in working.columns:
                working[col] = pd.to_numeric(working[col], errors="coerce").astype("float64")

        return working

    def _stabilize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self._stabilization_bars <= 0:
            return frame.copy(deep=True)
        total = frame.shape[0]
        if total <= self._stabilization_bars:
            return frame.iloc[0:0].copy(deep=True)
        return frame.iloc[: total - self._stabilization_bars].copy(deep=True)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _should_publish(frame: pd.DataFrame, publish_fingerprint: bool) -> bool:
        if not publish_fingerprint:
            return False
        if not isinstance(frame, pd.DataFrame):
            return False
        if frame.empty or "ts" not in frame.columns:
            return False
        return True

    def _frame_stats(self, frame: pd.DataFrame) -> _FrameStats:
        start = int(frame["ts"].min())
        end = int(frame["ts"].max())
        rows = int(frame.shape[0])
        return _FrameStats(start=start, end=end, rows=rows, as_of=self._now_iso())

    def _compute_fingerprint(
        self,
        *,
        stabilized: pd.DataFrame,
        node_id: str,
        interval: int,
        start: int,
        end: int,
    ) -> str:
        from qmtl.runtime.sdk.artifacts.fingerprint import compute_artifact_fingerprint

        fingerprint_metadata = {
            "node_id": node_id,
            "interval": int(interval),
            "coverage_bounds": (start, end),
            "conformance_version": self._conformance_version,
        }
        return compute_artifact_fingerprint(stabilized, fingerprint_metadata)

    def _build_manifest(
        self,
        *,
        node_id: str,
        interval: int,
        stats: _FrameStats,
        fingerprint: str,
        requested_range: tuple[int, int] | None,
        conformance_report: ConformanceReport | None,
    ) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "node_id": node_id,
            "range": [stats.start, stats.end],
            "row_count": stats.rows,
            "interval": int(interval),
            "dataset_fingerprint": fingerprint,
            "as_of": stats.as_of,
            "conformance_version": self._conformance_version,
            "stabilization_bars": self._stabilization_bars,
        }
        manifest["publication_watermark"] = self._now_iso()
        manifest["producer"] = {
            "identity": self._producer_identity,
            "node_id": node_id,
            "interval": int(interval),
        }
        if requested_range is not None:
            manifest["requested_range"] = [int(requested_range[0]), int(requested_range[1])]
        if conformance_report is not None:
            manifest["conformance"] = {
                "flags": dict(conformance_report.flags_counts),
                "warnings": list(conformance_report.warnings),
            }
        return manifest

    def _build_publication(
        self,
        *,
        fingerprint: str,
        stats: _FrameStats,
        node_id: str,
        uri: str | None,
        manifest: dict[str, Any],
    ) -> ArtifactPublication:
        return ArtifactPublication(
            dataset_fingerprint=fingerprint,
            as_of=stats.as_of,
            node_id=node_id,
            start=stats.start,
            end=stats.end,
            rows=stats.rows,
            uri=uri,
            manifest_uri=manifest.get("manifest_uri"),
            manifest=manifest,
        )

    async def _store_artifact(
        self, stabilized: pd.DataFrame, manifest: dict[str, Any], *, node_id: str
    ) -> str | None:
        if self._store is None:
            return None
        try:
            result = self._store(stabilized.copy(deep=True), manifest)
            if inspect.isawaitable(result):
                return await result  # type: ignore[return-value]
            return result
        except Exception:  # pragma: no cover - defensive logging only
            logger.exception("artifact store failure for node %s", node_id)
            return None


__all__ = ["ArtifactRegistrar", "ArtifactPublication"]
