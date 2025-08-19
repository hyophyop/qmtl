"""Run ``BinanceHistoryStrategy`` and expose Prometheus metrics."""

from strategies.dags.binance_history_dag import BinanceHistoryStrategy
from qmtl.sdk import Runner, metrics


def main() -> None:
    start_time = 0
    end_time = 1
    gateway_url = "http://localhost:8080"

    # Start the metrics server so Prometheus can scrape backfill statistics
    metrics.start_metrics_server(port=8000)

    Runner.backtest(
        BinanceHistoryStrategy,
        start_time=start_time,
        end_time=end_time,
        gateway_url=gateway_url,
    )

    # Collect key metrics such as ``backfill_jobs_in_progress``
    print(metrics.collect_metrics())


if __name__ == "__main__":
    main()
