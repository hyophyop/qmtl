from __future__ import annotations

import pandas as pd

from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner
from qmtl.runtime.io import QuestDBLoader, BinanceFetcher


fetcher = BinanceFetcher()
loader = QuestDBLoader(
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
    Runner.run(
        BackfillHistoryStrategy,
        world_id="backfill_history",
        gateway_url="http://localhost:8000",
    )


if __name__ == "__main__":
    main()
