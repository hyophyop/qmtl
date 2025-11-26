"""Backfill history example - QMTL v2.0."""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from qmtl.runtime.sdk import Runner, Strategy, Mode
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
    # v2 API: Submit with paper mode for history backfill
    result = Runner.submit(
        BackfillHistoryStrategy,
        world="backfill_history",
        mode=Mode.PAPER,
    )
    print(f"Strategy submitted: {result.status}")


if __name__ == "__main__":
    main()
