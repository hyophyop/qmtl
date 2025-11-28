from __future__ import annotations

"""GARCH(1,1) synthetic price path generator."""

import numpy as np

from .base import SyntheticInput


class GarchInput(SyntheticInput):
    """GARCH(1,1) price path generator."""

    def __init__(
        self,
        *,
        interval: int,
        period: int,
        start_price: float = 100.0,
        mu: float = 0.0,
        omega: float = 0.0001,
        alpha: float = 0.05,
        beta: float = 0.92,
        seed: int | None = None,
    ) -> None:
        super().__init__(interval=interval, period=period, seed=seed)
        self.price = start_price
        self.mu = mu
        self.omega = omega
        self.alpha = alpha
        self.beta = beta
        self.var = omega / (1 - alpha - beta)

    def step(self) -> tuple[int, dict[str, float | list[float]]]:
        interval = self._interval_value()
        eps = self.rng.standard_normal()
        self.var = self.omega + self.alpha * (eps ** 2) * self.var + self.beta * self.var
        ret = self.mu + np.sqrt(abs(self.var)) * eps
        self.price *= np.exp(ret)
        self.timestamp += interval
        return self.timestamp, {"price": float(self.price)}
