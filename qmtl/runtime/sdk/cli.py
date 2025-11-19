from __future__ import annotations
import argparse
import importlib

import asyncio
import logging
from typing import List
from .runner import Runner
from . import runtime
from . import configuration


logger = logging.getLogger(__name__)


def _parse_history_boundary(value: object | None, source: str) -> int | None:
    """Return an integer history boundary or ``None`` when unset/invalid."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-integer value for %s: %s", source, value)
        return None


def _resolve_history_bounds() -> tuple[int | None, int | None]:
    """Resolve history boundaries from the unified YAML configuration."""

    unified = configuration.get_runtime_config()
    if unified is None:
        return None, None

    test_cfg = unified.test
    start = _parse_history_boundary(getattr(test_cfg, "history_start", None), "test.history_start")
    end = _parse_history_boundary(getattr(test_cfg, "history_end", None), "test.history_end")
    return start, end


async def _main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qmtl tools sdk", description="Run QMTL strategy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run under WorldService decisions")
    run_p.add_argument("strategy", help="Import path as module:Class")
    run_p.add_argument("--world-id", required=True)
    run_p.add_argument("--gateway-url", required=True, help="Gateway base URL")
    run_p.add_argument("--no-ray", action="store_true", help="Disable Ray-based features")
    # Deprecated advanced options kept for CLI compatibility; ignored.
    run_p.add_argument("--mode", choices=["backtest", "dryrun", "live"], help=argparse.SUPPRESS)
    run_p.add_argument("--clock", choices=["virtual", "wall"], help=argparse.SUPPRESS)
    run_p.add_argument("--as-of", help=argparse.SUPPRESS)
    run_p.add_argument("--dataset-fingerprint", help=argparse.SUPPRESS)

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
        history_start, history_end = _resolve_history_bounds()
        if runtime.TEST_MODE and history_start is None and history_end is None:
            history_start, history_end = 1, 2
        await Runner.run_async(
            strategy_cls,
            world_id=args.world_id,
            gateway_url=args.gateway_url,
            history_start=history_start,
            history_end=history_end,
        )
    else:
        history_start, history_end = _resolve_history_bounds()
        if runtime.TEST_MODE and history_start is None and history_end is None:
            history_start, history_end = 1, 2
        await Runner.offline_async(
            strategy_cls,
            history_start=history_start,
            history_end=history_end,
        )
    return 0


def main(argv: List[str] | None = None) -> int:
    return asyncio.run(_main(argv))
