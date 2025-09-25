from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class ConformanceReport:
    warnings: tuple[str, ...] = ()
    flags_counts: dict[str, int] | None = None


class ConformancePipeline:
    """Lightweight normalization pipeline scaffold.

    This initial version is a no-op placeholder so that callers can route
    results through a stable interface without changing behavior. Future
    versions may enforce schema/time normalization and emit detailed reports.
    """

    def normalize(self, df: pd.DataFrame, *, schema: dict | None = None, interval: int | None = None) -> tuple[pd.DataFrame, ConformanceReport]:
        # Intentionally no-op for now to avoid changing behavior.
        return df, ConformanceReport()


__all__ = ["ConformancePipeline", "ConformanceReport"]

