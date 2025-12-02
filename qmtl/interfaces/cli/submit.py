from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import List

from qmtl.utils.i18n import _ as _t

from .common import parse_preset_overrides


def cmd_submit(argv: List[str]) -> int:
    """Submit a strategy for evaluation."""
    parser = argparse.ArgumentParser(
        prog="qmtl submit",
        description=_t("Submit a strategy for evaluation and activation"),
    )
    parser.add_argument(
        "strategy",
        help=_t("Strategy file path or module:class (e.g., my_strategy.py or strategies.my:MyStrategy)"),
    )
    parser.add_argument(
        "--world", "-w",
        default=None,
        help=_t("Target world (default: QMTL_DEFAULT_WORLD or __default__)"),
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["backtest", "paper", "live"],
        default="backtest",
        help=_t("Execution mode (default: backtest)"),
    )
    parser.add_argument(
        "--preset", "-p",
        choices=["sandbox", "conservative", "moderate", "aggressive"],
        default=None,
        help=_t("Policy preset to apply (defaults to server/world setting)"),
    )
    parser.add_argument(
        "--preset-mode",
        choices=["shared", "clone", "extend"],
        default=None,
        help=_t("How to apply preset world policy (metadata only)"),
    )
    parser.add_argument(
        "--preset-version",
        default=None,
        help=_t("Optional preset version identifier (metadata)"),
    )
    parser.add_argument(
        "--preset-override",
        action="append",
        default=[],
        help=_t("Override preset thresholds (key=value, e.g., max_drawdown.max=0.15)"),
    )
    
    args = parser.parse_args(argv)
    overrides = parse_preset_overrides(args.preset_override or [])
    strategy_cls = _load_strategy(args.strategy)
    if strategy_cls is None:
        print(_t("Error: Could not load strategy from '{}'").format(args.strategy), file=sys.stderr)
        return 1
    return _submit_and_print_result(strategy_cls, args, overrides)


def _submit_and_print_result(strategy_cls, args: argparse.Namespace, overrides: dict[str, float]) -> int:
    from qmtl.runtime.sdk import Runner, Mode

    try:
        result = Runner.submit(
            strategy_cls,
            world=args.world,
            mode=Mode(args.mode),
            preset=args.preset,
            preset_mode=args.preset_mode,
            preset_version=args.preset_version,
            preset_overrides=overrides or None,
        )
    except Exception as e:
        print(_t("Error: {}").format(str(e)), file=sys.stderr)
        return 1

    _print_submission_result(result)
    return 0 if result.status != "rejected" else 1


def _print_submission_result(result) -> None:
    print(_t("\n📊 Strategy Submission Result"))
    print("=" * 40)
    print(f"Strategy ID: {result.strategy_id}")
    print(f"Status:      {result.status}")
    print(f"World:       {result.world}")
    print(f"Mode:        {result.mode.value}")

    if result.status == "active":
        _print_active_result(result)
    elif result.status == "rejected":
        _print_rejected_result(result)
    else:
        print(f"\n⏳ Status: {result.status}")


def _print_active_result(result) -> None:
    print(_t("\n✅ Strategy activated successfully!"))
    if result.contribution is not None:
        print(f"Contribution: {result.contribution:.2%}")
    if result.weight is not None:
        print(f"Weight:       {result.weight:.2%}")
    if result.rank is not None:
        print(f"Rank:         #{result.rank}")


def _print_rejected_result(result) -> None:
    print(_t("\n❌ Strategy rejected"))
    if result.rejection_reason:
        print(f"Reason: {result.rejection_reason}")
    if result.improvement_hints:
        print(_t("\n💡 Improvement hints:"))
        for hint in result.improvement_hints:
            print(f"  - {hint}")


def _load_strategy(strategy_ref: str):
    """Load strategy class from file path or module:class reference."""
    if _is_strategy_file(strategy_ref):
        return _load_strategy_from_file(Path(strategy_ref))
    return _load_strategy_from_module_ref(strategy_ref)


def _is_strategy_file(strategy_ref: str) -> bool:
    return strategy_ref.endswith(".py") or Path(strategy_ref).exists()


def _load_strategy_from_file(path: Path):
    import importlib.util
    if not path.exists():
        return None

    spec = importlib.util.spec_from_file_location("strategy_module", path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules["strategy_module"] = module
    spec.loader.exec_module(module)

    from qmtl.runtime.sdk import Strategy
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
            return obj
    return None


def _load_strategy_from_module_ref(strategy_ref: str):
    if ":" in strategy_ref:
        module_path, class_name = strategy_ref.rsplit(":", 1)
    else:
        parts = strategy_ref.rsplit(".", 1)
        if len(parts) != 2:
            return None
        module_path, class_name = parts

    try:
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError):
        return None
