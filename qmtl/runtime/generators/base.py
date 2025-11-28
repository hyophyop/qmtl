from __future__ import annotations

"""Base utilities for synthetic data generators."""

import numpy as np

from qmtl.runtime.sdk.node import StreamInput


class SyntheticInput(StreamInput):
    """Base class for synthetic :class:`~qmtl.runtime.sdk.node.StreamInput` generators."""

    def __init__(self, *, interval: int, period: int, seed: int | None = None) -> None:
        super().__init__(interval=interval, period=period)
        self.rng = np.random.default_rng(seed)
        self.timestamp = 0

    def _interval_value(self) -> int:
        interval = self.interval
        if not isinstance(interval, int):
            raise TypeError("SyntheticInput requires an integer interval")
        return interval

    def step(self) -> tuple[int, dict[str, float | list[float]]]:
        raise NotImplementedError

    def generate(self, steps: int) -> list[tuple[int, dict[str, float | list[float]]]]:
        data: list[tuple[int, dict[str, float | list[float]]]] = []
        for _ in range(steps):
            data.append(self.step())
        return data
