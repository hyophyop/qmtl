import argparse
import importlib

import asyncio
from .runner import Runner


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run QMTL strategy")
    parser.add_argument("strategy", help="Import path as module:Class")
    parser.add_argument("--mode", choices=["backtest", "dryrun", "live", "offline"], required=True)
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--on-missing", default="skip")
    parser.add_argument("--gateway-url")
    parser.add_argument("--backfill-source")
    parser.add_argument("--backfill-start", type=int)
    parser.add_argument("--backfill-end", type=int)
    args = parser.parse_args()

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
            backfill_source=args.backfill_source,
            backfill_start=args.backfill_start,
            backfill_end=args.backfill_end,
        )
    elif args.mode == "dryrun":
        await Runner.dryrun_async(
            strategy_cls,
            gateway_url=args.gateway_url,
            backfill_source=args.backfill_source,
            backfill_start=args.backfill_start,
            backfill_end=args.backfill_end,
        )
    elif args.mode == "live":
        await Runner.live_async(
            strategy_cls,
            gateway_url=args.gateway_url,
            backfill_source=args.backfill_source,
            backfill_start=args.backfill_start,
            backfill_end=args.backfill_end,
        )
    else:  # offline
        Runner.offline(strategy_cls)

def main() -> None:
    asyncio.run(_main())
