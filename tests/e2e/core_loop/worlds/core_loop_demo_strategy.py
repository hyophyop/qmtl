from __future__ import annotations

from qmtl.runtime.sdk import Mode, Runner, Strategy, StreamInput


class CoreLoopDemoStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["core-loop-demo"], interval="60s", period=1)
        self.add_nodes([price])


if __name__ == "__main__":
    Runner.submit(CoreLoopDemoStrategy, world="core-loop-demo", mode=Mode.BACKTEST)
