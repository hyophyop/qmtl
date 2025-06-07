import argparse
import importlib

from .runner import Runner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QMTL strategy")
    parser.add_argument("strategy", help="Import path as module:Class")
    parser.add_argument("--mode", choices=["backtest", "dryrun", "live"], required=True)
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--on-missing", default="skip")
    args = parser.parse_args()

    module_name, class_name = args.strategy.split(":")
    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)

    if args.mode == "backtest":
        Runner.backtest(strategy_cls, start_time=args.start_time, end_time=args.end_time, on_missing=args.on_missing)
    elif args.mode == "dryrun":
        Runner.dryrun(strategy_cls)
    elif args.mode == "live":
        Runner.live(strategy_cls)
