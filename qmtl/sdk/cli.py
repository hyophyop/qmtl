from __future__ import annotations
import argparse
import importlib

import asyncio
from typing import List
from .runner import Runner


async def _main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="qmtl sdk",
        description="Run QMTL strategy (backtest/dry-run/live/offline)",
    )
    parser.add_argument("strategy", help="Import path as module:Class")
    parser.add_argument(
        "--mode",
        choices=["backtest", "dryrun", "live", "offline"],
        required=True,
        help=(
            "Execution mode: backtest replays history, dryrun connects to the Gateway without trading, "
            "live executes with real queues, offline runs locally without Gateway"
        ),
    )
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--on-missing", default="skip")
    parser.add_argument(
        "--gateway-url",
        help="Gateway base URL (required for backtest, dryrun and live modes)",
    )
    parser.add_argument(
        "--with-ray",
        action="store_true",
        help="Enable Ray-based execution of compute functions",
    )
    args = parser.parse_args(argv)

    if args.with_ray:
        Runner.enable_ray()

    module_name, class_name = args.strategy.split(":")
    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)

    if args.mode == "backtest":
        await Runner.backtest_async(
            strategy_cls,
            start_time=args.start_time,
            end_time=args.end_time,
            on_missing=args.on_missing,
            gateway_url=args.gateway_url,
        )
    elif args.mode == "dryrun":
        await Runner.dryrun_async(
            strategy_cls,
            gateway_url=args.gateway_url,
        )
    elif args.mode == "live":
        await Runner.live_async(
            strategy_cls,
            gateway_url=args.gateway_url,
        )
    else:  # offline
        await Runner.offline_async(strategy_cls)

def main(argv: List[str] | None = None) -> None:
    asyncio.run(_main(argv))

