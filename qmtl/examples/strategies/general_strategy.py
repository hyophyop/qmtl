import argparse
import pandas as pd
from qmtl.runtime.io import QuestDBLoader, QuestDBRecorder
from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner, EventRecorderService

class GeneralStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="60s", default_period=30)

    def setup(self):
        price_stream = StreamInput(
            history_provider=QuestDBLoader(
                dsn="postgresql://localhost:8812/qdb",
            ),
            event_service=EventRecorderService(
                QuestDBRecorder(
                    dsn="postgresql://localhost:8812/qdb",
                )
            ),
        )

        def generate_signal(view):
            price = pd.DataFrame([v for _, v in view[price_stream][60]])
            momentum = price["close"].pct_change().rolling(5).mean()
            signal = (momentum > 0).astype(int)
            return pd.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )
        self.add_nodes([price_stream, signal_node])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-id")
    parser.add_argument("--gateway-url")
    args = parser.parse_args()

    if args.world_id and args.gateway_url:
        Runner.run(
            GeneralStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(GeneralStrategy)
