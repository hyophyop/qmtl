"""Example strategy that can run under WS or offline."""

import argparse
from qmtl.runtime.sdk import Strategy, StreamInput, Runner


class ValidationStrategy(Strategy):
    """Minimal strategy containing a single price stream."""

    def setup(self):
        price = StreamInput(interval="60s", period=20)
        self.add_nodes([price])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world-id")
    parser.add_argument("--gateway-url")
    args = parser.parse_args()

    if args.world_id and args.gateway_url:
        Runner.run(
            ValidationStrategy,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        Runner.offline(ValidationStrategy)


if __name__ == "__main__":
    main()
