from __future__ import annotations

"""Heston model synthetic price path generator."""

import numpy as np

from .base import SyntheticInput


class HestonInput(SyntheticInput):
    """Heston model price path generator."""

    def __init__(
        self,
        *,
        interval: int,
        period: int,
        start_price: float = 100.0,
        v0: float = 0.04,
        kappa: float = 2.0,
        theta: float = 0.04,
        sigma: float = 0.5,
        rho: float = -0.7,
        mu: float = 0.0,
        seed: int | None = None,
    ) -> None:
        super().__init__(interval=interval, period=period, seed=seed)
        self.price = start_price
        self.v = v0
        self.kappa = kappa
        self.theta = theta
        self.sigma = sigma
        self.rho = rho
        self.mu = mu

    def step(self) -> tuple[int, dict[str, float]]:
        dt = float(self.interval)
        z1 = self.rng.standard_normal()
        z2 = self.rng.standard_normal()
        dw1 = np.sqrt(dt) * z1
        dw2 = np.sqrt(dt) * (self.rho * z1 + np.sqrt(1 - self.rho ** 2) * z2)
        self.v = abs(
            self.v + self.kappa * (self.theta - self.v) * dt + self.sigma * np.sqrt(abs(self.v)) * dw2
        )
        self.price *= np.exp((self.mu - 0.5 * self.v) * dt + np.sqrt(abs(self.v)) * dw1)
        self.timestamp += self.interval
        return self.timestamp, {"price": float(self.price)}
