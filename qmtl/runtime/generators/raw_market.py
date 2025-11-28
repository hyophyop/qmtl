from __future__ import annotations

"""Synthetic raw market data generator."""

from typing import Dict, List, Tuple

from .base import SyntheticInput


class RawMarketInput(SyntheticInput):
    """Generate random walk price and basic order flow statistics."""

    def __init__(
        self,
        *,
        interval: int,
        period: int,
        start_price: float = 100.0,
        seed: int | None = None,
    ) -> None:
        super().__init__(interval=interval, period=period, seed=seed)
        self.price = start_price

    def step(self) -> Tuple[int, Dict[str, float | List[float]]]:
        interval = self._interval_value()
        self.timestamp += interval
        # Random walk price dynamics
        ret = self.rng.normal(0, 0.1)
        self.price += ret
        volume = float(self.rng.integers(50, 150))
        buy_volume = float(self.rng.integers(0, int(volume)))
        sell_volume = volume - buy_volume
        bid_volume = float(self.rng.integers(50, 150))
        ask_volume = float(self.rng.integers(50, 150))
        depth_change = float(self.rng.normal())
        impact = abs(ret) / volume if volume else 0.0
        spread = 0.01
        taker_fee = 0.001
        # z-score placeholders
        def z_scores(prefix: str) -> Dict[str, float]:
            keys = [
                "C",
                "Cliff",
                "Gap",
                "CH",
                "RL",
                "Shield",
                "QDT_inv",
                "Pers",
                "OFI",
                "MicroSlope",
                "AggFlow",
            ]
            return {f"{prefix}_z_{k}": float(self.rng.normal()) for k in keys}

        return (
            self.timestamp,
            {
                "price": float(self.price),
                "volume": volume,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "depth_change": depth_change,
                "impact": impact,
                "spread": spread,
                "taker_fee": taker_fee,
                **z_scores("ask"),
                **z_scores("bid"),
            },
        )

__all__ = ["RawMarketInput"]
