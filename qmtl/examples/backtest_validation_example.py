"""Backtest example with pre-run data validation."""

from qmtl.sdk.backtest_validation import validate_backtest_data

import argparse
from qmtl.examples.defaults import load_backtest_defaults
from qmtl.sdk import Strategy, StreamInput, Runner


class ValidationStrategy(Strategy):
    """Minimal strategy containing a single price stream."""

    def setup(self):
        price = StreamInput(interval="60s", period=20)
        self.add_nodes([price])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest", action="store_true", help="Run backtest")
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--on-missing")
    args = parser.parse_args()

    defaults = load_backtest_defaults(__file__)
    start = args.start_time or defaults.get("start_time")
    end = args.end_time or defaults.get("end_time")
    on_missing = args.on_missing or defaults.get("on_missing", "skip")
    
    if args.backtest:
        strategy = ValidationStrategy()
        strategy.setup()
        validate_backtest_data(strategy)
        Runner.backtest(
            ValidationStrategy,
            start_time=start,
            end_time=end,
            on_missing=on_missing,
            validate_data=True,
        )
    else:
        Runner.offline(ValidationStrategy)


if __name__ == "__main__":
    main()
