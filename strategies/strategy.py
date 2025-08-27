"""Run configured strategies and expose Prometheus metrics."""

from strategies.config import load_config
from strategies.registry import registry
try:
    from qmtl.sdk import Runner, metrics  # type: ignore
except ImportError:
    # Handle import error gracefully
    Runner = None  # type: ignore
    metrics = None  # type: ignore


def main() -> None:
    """Main function to run configured strategies."""
    if Runner is None or metrics is None:
        print("Error: qmtl.sdk modules not available")
        return

    cfg = load_config()
    backtest_cfg = cfg.get("backtest", {})
    start_time = backtest_cfg.get("start_time")
    end_time = backtest_cfg.get("end_time")
    gateway_url = cfg.get("gateway_url")

    dags_cfg = cfg.get("dags", {})

    # Start the metrics server so Prometheus can scrape backfill statistics
    metrics.start_metrics_server(port=8000)

    # Dynamically load and run strategies based on configuration
    for strategy_name, enabled in dags_cfg.items():
        if enabled and registry.has_strategy(strategy_name):
            strategy_class = registry.get_strategy(strategy_name)
            print(f"Running strategy: {strategy_name}")

            Runner.backtest(  # type: ignore
                strategy_class,
                start_time=start_time,
                end_time=end_time,
                gateway_url=gateway_url,
            )
        elif enabled:
            print(f"Warning: Strategy '{strategy_name}' not found in registry")

    # Collect key metrics such as backfill_jobs_in_progress
    print(metrics.collect_metrics())


if __name__ == "__main__":
    main()
