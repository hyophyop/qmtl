"""Backfill history example - QMTL v2.0."""

from __future__ import annotations

import pandas as pd

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.io import QuestDBHistoryProvider, BinanceFetcher


fetcher = BinanceFetcher()
loader = QuestDBHistoryProvider(
    dsn="postgresql://localhost:8812/qdb",
    fetcher=fetcher,
)


class BackfillHistoryStrategy(Strategy):
    def setup(self) -> None:
        self.price = StreamInput(
            interval="1m",
            period=60,
            history_provider=loader,
        )

        def pct_change(view) -> pd.DataFrame:
            df = pd.DataFrame([v for _, v in view[self.price][60]])
            return pd.DataFrame({"ret": df["close"].pct_change()})

        ret_node = Node(input=self.price, compute_fn=pct_change, name="returns")
        self.add_nodes([self.price, ret_node])


def main() -> None:
    # v2 API: submit to WorldService; stage is governed by world policy
    result = Runner.submit(
        BackfillHistoryStrategy,
        world="backfill_history",
    )
    print(f"Strategy submitted: {result.status}")


if __name__ == "__main__":
    main()
