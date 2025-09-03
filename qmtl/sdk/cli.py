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

    off_p = sub.add_parser("offline", help="Run locally without Gateway/WS")
    off_p.add_argument("strategy", help="Import path as module:Class")
    off_p.add_argument("--no-ray", action="store_true", help="Disable Ray-based features")

    args = parser.parse_args(argv)

    if args.no_ray:
        runtime.NO_RAY = True

    module_name, class_name = args.strategy.split(":")
    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)

    if args.cmd == "run":
        await Runner.run_async(
            strategy_cls,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
        )
    else:
        await Runner.offline_async(strategy_cls)
    return 0


def main(argv: List[str] | None = None) -> int:
    return asyncio.run(_main(argv))
