from __future__ import annotations

"""Synthetic data generators for strategy testing."""

import numpy as np

from qmtl.sdk.node import StreamInput


class SyntheticInput(StreamInput):
    """Base class for synthetic StreamInput generators."""

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

    def step(self) -> tuple[int, dict[str, float]]:
        eps = self.rng.standard_normal()
        self.var = self.omega + self.alpha * (eps ** 2) * self.var + self.beta * self.var
        ret = self.mu + np.sqrt(abs(self.var)) * eps
        self.price *= np.exp(ret)
        self.timestamp += self.interval
        return self.timestamp, {"price": float(self.price)}


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

    def step(self) -> tuple[int, dict[str, float]]:
        dt = float(self.interval)
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
        self.timestamp += self.interval
        return self.timestamp, {"price": float(self.price)}


