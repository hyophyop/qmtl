from __future__ import annotations

"""Helpers for publishing stabilized Seamless artifacts."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import inspect
import io
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
    ) -> None:
        if stabilization_bars < 0:
            raise ValueError("stabilization_bars must be >= 0")
        self._store = store
        self._stabilization_bars = int(stabilization_bars)
        self._conformance_version = str(conformance_version)
        self._float_format = float_format

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
    ) -> ArtifactPublication | None:
        """Stabilize ``frame`` and return publication metadata.

        When ``store`` was supplied at construction time the stabilized frame and
        manifest metadata are handed to it. Failures during persistence are
        logged and do not raise.
        """

        if not isinstance(frame, pd.DataFrame) or frame.empty or "ts" not in frame.columns:
            return None

        canonical = self._canonicalize_frame(frame)
        stabilized = self._stabilize_frame(canonical)
        if stabilized.empty:
            return None

        start = int(stabilized["ts"].min())
        end = int(stabilized["ts"].max())
        rows = int(stabilized.shape[0])
        as_of = self._now_iso()
        fingerprint = self._compute_fingerprint(stabilized)

        manifest: dict[str, Any] = {
            "node_id": node_id,
            "range": [start, end],
            "row_count": rows,
            "interval": int(interval),
            "dataset_fingerprint": fingerprint,
            "as_of": as_of,
            "conformance_version": self._conformance_version,
            "stabilization_bars": self._stabilization_bars,
        }
        if requested_range is not None:
            manifest["requested_range"] = [int(requested_range[0]), int(requested_range[1])]
        if conformance_report is not None:
            manifest["conformance"] = {
                "flags": dict(conformance_report.flags_counts),
                "warnings": list(conformance_report.warnings),
            }

        uri: str | None = None
        if self._store is not None:
            try:
                result = self._store(stabilized.copy(deep=True), manifest)
                if inspect.isawaitable(result):
                    uri = await result  # type: ignore[assignment]
                else:
                    uri = result
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception("artifact store failure for node %s", node_id)

        return ArtifactPublication(
            dataset_fingerprint=fingerprint,
            as_of=as_of,
            node_id=node_id,
            start=start,
            end=end,
            rows=rows,
            uri=uri,
            manifest_uri=manifest.get("manifest_uri"),
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

    def _compute_fingerprint(self, frame: pd.DataFrame) -> str:
        buffer = io.StringIO()
        frame.to_csv(buffer, index=False, header=True, float_format=self._float_format)
        data = buffer.getvalue().encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = ["ArtifactRegistrar", "ArtifactPublication"]
