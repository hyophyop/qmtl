from .strategy import Strategy


class Runner:
    """Execute strategies in various modes."""

    @staticmethod
    def _prepare(strategy_cls: type[Strategy]) -> Strategy:
        strategy = strategy_cls()
        strategy.setup()
        strategy.define_execution()
        return strategy

    @staticmethod
    def backtest(strategy_cls: type[Strategy], start_time=None, end_time=None, on_missing="skip") -> Strategy:
        """Run strategy in backtest mode."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[BACKTEST] {strategy_cls.__name__} from {start_time} to {end_time} on_missing={on_missing}")
        # Placeholder for backtest logic
        return strategy

    @staticmethod
    def dryrun(strategy_cls: type[Strategy]) -> Strategy:
        """Run strategy in dry-run (paper trading) mode."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[DRYRUN] {strategy_cls.__name__} starting")
        # Placeholder for dry-run logic
        return strategy

    @staticmethod
    def live(strategy_cls: type[Strategy]) -> Strategy:
        """Run strategy in live trading mode."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[LIVE] {strategy_cls.__name__} starting")
        # Placeholder for live trading logic
        return strategy
