from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import List
from qmtl.utils.i18n import _ as _t

from .common import parse_preset_overrides


def _discover_project_settings() -> tuple[Path | None, str | None]:
    """Return (strategy_root, default_world) from config/env if present."""

    from qmtl.runtime.sdk.configuration import (
        get_runtime_config,
        get_runtime_config_path,
    )

    env_strategy_root = os.environ.get("QMTL_STRATEGY_ROOT")
    strategy_root: Path | None = (
        Path(env_strategy_root).expanduser().resolve()
        if env_strategy_root is not None
        else None
    )

    config = get_runtime_config()
    if config is None:
        return strategy_root, None

    cfg_path = get_runtime_config_path()
    base_dir = Path(cfg_path).parent if cfg_path else Path.cwd()
    if config.project.strategy_root:
        strategy_root = (base_dir / config.project.strategy_root).expanduser().resolve()
    return strategy_root, config.project.default_world


def _prepend_strategy_root(strategy_root: Path | None) -> None:
    """Ensure strategy_root is at the front of sys.path when provided."""

    if strategy_root is None:
        return

    root_str = str(strategy_root)
    candidates: list[str] = []

    parent = strategy_root.parent
    parent_str = str(parent)
    if parent != strategy_root and parent_str not in sys.path:
        candidates.append(parent_str)
    if root_str not in sys.path:
        candidates.append(root_str)

    if candidates:
        sys.path[:0] = candidates


def cmd_submit(argv: List[str]) -> int:
    """Submit a strategy for evaluation."""
    strategy_root, config_default_world = _discover_project_settings()
    default_world = config_default_world or os.environ.get("QMTL_DEFAULT_WORLD") or "__default__"

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
        default=default_world,
        help=_t(
            "Target world (defaults to project.default_world in qmtl.yml or QMTL_DEFAULT_WORLD)"
        ),
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["backtest", "paper", "live"],
        default="backtest",
        help=_t(
            "Execution mode (backtest|paper|live). WS effective_mode is authoritative; "
            "missing/legacy tokens are normalized to compute-only (backtest)."
        ),
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
        "--data-preset",
        default=None,
        help=_t("World data preset id (world.data.presets[].id). Defaults to the world's first preset."),
    )
    parser.add_argument(
        "--preset-override",
        action="append",
        default=[],
        help=_t("Override preset thresholds (key=value, e.g., max_drawdown.max=0.15)"),
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help=_t("Output format (text|json). Default: text"),
    )
    
    args = parser.parse_args(argv)
    args.world = (args.world or "").strip()
    if not args.world:
        print(_t("Error: world must be provided (use --world or set QMTL_DEFAULT_WORLD)"), file=sys.stderr)
        return 1
    _prepend_strategy_root(strategy_root)
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
            data_preset=args.data_preset,
        )
    except Exception as e:
        print(_t("Error: {}").format(str(e)), file=sys.stderr)
        return 1

    if getattr(result, "downgraded", False) or getattr(result, "safe_mode", False):
        reason = getattr(result, "downgrade_reason", None) or "unspecified"
        print(_t("⚠️  Safe mode: execution was downgraded ({})").format(reason), file=sys.stderr)

    _emit_submission_result(result, getattr(args, "output", "text"))
    return 0 if result.status != "rejected" else 1


def _emit_submission_result(result, output_format: str = "text") -> None:
    if output_format == "json":
        _print_submission_result_json(result)
        return
    _print_submission_result(result)


def _print_submission_result(result) -> None:
    print(_t("\n📊 Strategy Submission Result"))
    print("=" * 40)
    print(f"Strategy ID: {result.strategy_id}")
    print(f"Status:      {result.status}")
    print(f"World:       {result.world}")
    print(f"Mode:        {result.mode.value}")
    if getattr(result, "downgraded", False) or getattr(result, "safe_mode", False):
        reason = getattr(result, "downgrade_reason", None) or "unspecified"
        print(f"Safe mode:   downgraded ({reason})")

    _print_ws_section(result)
    if getattr(result, "precheck", None):
        _print_precheck_section(result.precheck)


def _print_submission_result_json(result) -> None:
    """Emit SubmitResult as JSON with WS/precheck separation preserved."""
    try:
        payload = result.to_dict()
    except Exception:
        payload = result
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_ws_section(result) -> None:
    print(_t("\n🌐 WorldService decision (SSOT)"))
    print(f"Status: {result.status}")
    if result.status == "rejected" and result.rejection_reason:
        print(f"Reason: {result.rejection_reason}")
    if result.threshold_violations:
        _print_thresholds(result.threshold_violations, label=_t("Threshold violations (WS)"))
    if result.status == "active":
        _print_active_result(result)
    elif result.status == "rejected":
        _print_rejected_result(result)
    else:
        print(f"{_t('Waiting for WS decision or pending activation.')} {_t('Local pre-check shown below if available.')}")


def _print_active_result(result) -> None:
    print(_t("✅ Strategy activated successfully!"))
    if result.contribution is not None:
        print(f"Contribution: {result.contribution:.2%}")
    if result.weight is not None:
        print(f"Weight:       {result.weight:.2%}")
    if result.rank is not None:
        print(f"Rank:         #{result.rank}")


def _print_rejected_result(result) -> None:
    print(_t("❌ Strategy rejected"))
    if result.improvement_hints:
        print(_t("\n💡 Improvement hints:"))
        for hint in result.improvement_hints:
            print(f"  - {hint}")
    if result.threshold_violations:
        _print_thresholds(result.threshold_violations, label=_t("Threshold violations (WS)"))


def _print_precheck_section(precheck) -> None:
    print(_t("\n🧪 Local pre-check (ValidationPipeline)"))
    print(f"Status: {precheck.status}")
    if precheck.contribution is not None:
        print(f"Contribution: {precheck.contribution:.2%}")
    if precheck.weight is not None:
        print(f"Weight:       {precheck.weight:.2%}")
    if precheck.rank is not None:
        print(f"Rank:         #{precheck.rank}")
    if precheck.correlation_avg is not None:
        print(f"Correlation:  {precheck.correlation_avg:.2f}")
    if precheck.violations:
        _print_thresholds(precheck.violations, label=_t("Threshold violations (pre-check)"))
    if precheck.improvement_hints:
        print(_t("\nHints (pre-check):"))
        for hint in precheck.improvement_hints:
            print(f"  - {hint}")


def _print_thresholds(violations: list[dict], *, label: str) -> None:
    if not violations:
        return
    print(label + ":")
    for v in violations:
        metric = v.get("metric", "metric")
        vtype = v.get("threshold_type") or v.get("type") or "threshold"
        tval = v.get("threshold_value") or v.get("threshold")
        value = v.get("value")
        message = v.get("message")
        line = f"  - {metric} {vtype} {tval}"
        if value is not None:
            line += f" (value={value})"
        if message:
            line += f" — {message}"
        print(line)


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
