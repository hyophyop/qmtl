from __future__ import annotations

"""Base utilities for synthetic data generators."""

import numpy as np

from qmtl.sdk.node import StreamInput


class SyntheticInput(StreamInput):
    """Base class for synthetic :class:`~qmtl.sdk.node.StreamInput` generators."""

    def __init__(self, *, interval: int, period: int, seed: int | None = None) -> None:
        super().__init__(interval=interval, period=period)
        self.rng = np.random.default_rng(seed)
        self.timestamp = 0

    def step(self) -> tuple[int, dict[str, float]]:
        raise NotImplementedError

    def generate(self, steps: int) -> list[tuple[int, dict[str, float]]]:
        data = []
        for _ in range(steps):
            data.append(self.step())
        return data
