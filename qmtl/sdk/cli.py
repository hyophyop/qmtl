from __future__ import annotations
import argparse
import importlib

import asyncio
import logging
from typing import List
from .runner import Runner
from . import runtime


logger = logging.getLogger(__name__)


async def _main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qmtl sdk", description="Run QMTL strategy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run under WorldService decisions")
    run_p.add_argument("strategy", help="Import path as module:Class")
    run_p.add_argument("--world-id", required=True)
    run_p.add_argument("--gateway-url", required=True, help="Gateway base URL")
    run_p.add_argument("--no-ray", action="store_true", help="Disable Ray-based features")
    run_p.add_argument("--history-start", dest="history_start", help="Explicit history start (test/deterministic runs)")
    run_p.add_argument("--history-end", dest="history_end", help="Explicit history end (test/deterministic runs)")
    run_p.add_argument(
        "--fail-on-history-gap",
        action="store_true",
        help="Raise error if history gaps remain after warm-up",
    )

    off_p = sub.add_parser("offline", help="Run locally without Gateway/WS")
    off_p.add_argument("strategy", help="Import path as module:Class")
    off_p.add_argument("--no-ray", action="store_true", help="Disable Ray-based features")
    off_p.add_argument(
        "--fail-on-history-gap",
        action="store_true",
        help="Raise error if history gaps remain after warm-up",
    )

    args = parser.parse_args(argv)

    if args.no_ray:
        runtime.NO_RAY = True
    if getattr(args, "fail_on_history_gap", False):
        runtime.FAIL_ON_HISTORY_GAP = True

    module_name, class_name = args.strategy.split(":")
    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)

    if args.cmd == "run":
        # In test mode, default to deterministic placeholders when not provided
        h_start = args.history_start
        h_end = args.history_end
        if runtime.TEST_MODE and h_start is None and h_end is None:
            h_start, h_end = "1", "2"
        await Runner.run_async(
            strategy_cls,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
            history_start=h_start,
            history_end=h_end,
        )
    else:
        await Runner.offline_async(strategy_cls)
    return 0


def main(argv: List[str] | None = None) -> int:
    return asyncio.run(_main(argv))
