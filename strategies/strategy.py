"""Run ``BinanceHistoryStrategy`` and expose Prometheus metrics."""

from strategies.config import load_config
from strategies.dags.binance_history_dag import BinanceHistoryStrategy
from qmtl.sdk import Runner, metrics


def main() -> None:
    cfg = load_config()
    backtest_cfg = cfg.get("backtest", {})
    start_time = backtest_cfg.get("start_time")
    end_time = backtest_cfg.get("end_time")
    gateway_url = cfg.get("gateway_url")

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
