from __future__ import annotations

"""Rough Bergomi model synthetic price path generator."""

import numpy as np

from .base import SyntheticInput


class RoughBergomiInput(SyntheticInput):
    """Rough Bergomi model price path generator."""

    def __init__(
        self,
        *,
        interval: int,
        period: int,
        start_price: float = 100.0,
        xi: float = 0.04,
        eta: float = 1.5,
        H: float = 0.1,
        rho: float = -0.7,
        mu: float = 0.0,
        seed: int | None = None,
    ) -> None:
        super().__init__(interval=interval, period=period, seed=seed)
        self.price = start_price
        self.xi = xi
        self.eta = eta
        self.H = H
        self.rho = rho
        self.mu = mu
        self.w1 = 0.0
        self.wfbm = 0.0
        self.t = 0.0

    def step(self) -> tuple[int, dict[str, float | list[float]]]:
        interval = self._interval_value()
        dt = float(interval)
        z1 = self.rng.standard_normal()
        z2 = self.rng.standard_normal()
        dw1 = np.sqrt(dt) * z1
        dwfbm = (dt ** self.H) * z2
        self.w1 += dw1
        self.wfbm += dwfbm
        t_new = self.t + dt
        v = self.xi * np.exp(self.eta * self.wfbm - 0.5 * self.eta ** 2 * t_new ** (2 * self.H))
        corr_term = self.rho * z1 + np.sqrt(1 - self.rho ** 2) * self.rng.standard_normal()
        self.price *= np.exp((self.mu - 0.5 * v) * dt + np.sqrt(v * dt) * corr_term)
        self.t = t_new
        self.timestamp += interval
        return self.timestamp, {"price": float(self.price)}
