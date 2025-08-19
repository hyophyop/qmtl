"""Run BinanceHistoryStrategy backtest."""

from strategies.dags.binance_history_dag import BinanceHistoryStrategy
from qmtl.sdk import Runner


def main() -> None:
    start_time = 0
    end_time = 1
    gateway_url = "http://localhost:8080"
    Runner.backtest(
        BinanceHistoryStrategy,
        start_time=start_time,
        end_time=end_time,
        gateway_url=gateway_url,
    )


if __name__ == "__main__":
    main()
