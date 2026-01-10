from __future__ import annotations

from qmtl.runtime.sdk import Strategy, StreamInput


class DistillationStrategyAlpha(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["distill-alpha"], interval="60s", period=1)
        self.add_nodes([price])


class DistillationStrategyBeta(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["distill-beta"], interval="60s", period=1)
        self.add_nodes([price])


class DistillationStrategyGamma(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["distill-gamma"], interval="60s", period=1)
        self.add_nodes([price])
