from __future__ import annotations

"""Interfaces and key definitions for the Feature Artifact Plane."""

from dataclasses import dataclass
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class FeatureArtifactKey:
    """Uniquely identify an immutable feature artifact."""

    factor: str
    interval: int
    params: str
    instrument: str
    timestamp: int
    dataset_fingerprint: str
    version: int = 1


class FeatureStoreBackend(Protocol):
    """Storage backend contract for feature artifacts."""

    def write(self, key: FeatureArtifactKey, payload: Any) -> None:
        """Persist ``payload`` under ``key``."""

    def load_series(
        self,
        *,
        factor: str,
        interval: int,
        params: str,
        instrument: str,
        dataset_fingerprint: str,
        start: int | None = None,
        end: int | None = None,
    ) -> list[tuple[int, Any]]:
        """Return artifacts ordered by timestamp."""

    def list_instruments(
        self,
        *,
        factor: str,
        params: str,
        dataset_fingerprint: str,
    ) -> Iterable[str]:
        """Return known instruments for the given factor."""

    def count(
        self,
        *,
        factor: str,
        interval: int,
        params: str,
        instrument: str,
        dataset_fingerprint: str,
    ) -> int:
        """Return number of stored artifacts for the selection."""
