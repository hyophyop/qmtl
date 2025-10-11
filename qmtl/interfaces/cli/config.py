from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
from typing import Dict, Iterable, List, Mapping

from qmtl.foundation.config import find_config_file, load_config
from qmtl.foundation.config_validation import (
    ValidationIssue,
    validate_dagmanager_config,
    validate_gateway_config,
)

_STATUS_LABELS = {
    "ok": "OK",
    "warning": "WARN",
    "error": "ERROR",
}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl config", add_help=True)
    parser.description = textwrap.dedent(
        """
        Configuration utilities.

        Subcommands:
          validate  Check connectivity and readiness for Gateway and DAG Manager.
        """
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["validate"],
        help="Subcommand to run",
    )
    return parser


def _build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl config validate")
    parser.add_argument(
        "--config",
        help="Path to configuration file (defaults to qmtl.yml in CWD)",
    )
    parser.add_argument(
        "--target",
        choices=["gateway", "dagmanager", "all"],
        default="all",
        help="Limit validation to a specific service",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip network-dependent checks (assume services are offline)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit validation report as JSON in addition to the table",
    )
    return parser


def _issues_to_json(results: Mapping[str, Mapping[str, ValidationIssue]]) -> Dict[str, object]:
    data: Dict[str, Dict[str, Dict[str, str]]] = {}
    overall = "ok"
    for target, checks in results.items():
        data[target] = {
            name: {"severity": issue.severity, "hint": issue.hint}
            for name, issue in checks.items()
        }
        if any(issue.severity == "error" for issue in checks.values()):
            overall = "error"
    return {"status": overall, "results": data}


def _format_checks(checks: Mapping[str, ValidationIssue]) -> Iterable[str]:
    if not checks:
        return ["  (no checks executed)"]
    width = max(len(name) for name in checks)
    for name, issue in checks.items():
        label = _STATUS_LABELS.get(issue.severity, issue.severity.upper())
        yield f"  {name.ljust(width)}  {label:<5}  {issue.hint}"


def _render_table(results: Mapping[str, Mapping[str, ValidationIssue]]) -> str:
    lines: List[str] = []
    for target, checks in results.items():
        lines.append(f"{target}:")
        lines.extend(_format_checks(checks))
        lines.append("")
    return "\n".join(lines).strip()


async def _execute_validate(args: argparse.Namespace) -> Mapping[str, Mapping[str, ValidationIssue]]:
    cfg_path = args.config or find_config_file()
    if not cfg_path:
        print("[qmtl] Configuration file not found. Specify --config.", file=sys.stderr)
        raise SystemExit(2)

    try:
        unified = load_config(cfg_path)
    except FileNotFoundError:
        print(f"[qmtl] Configuration file '{cfg_path}' does not exist.", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:  # pragma: no cover - defensive catch
        print(f"[qmtl] Failed to load configuration: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    targets: List[str] = []
    if args.target in {"gateway", "all"}:
        targets.append("gateway")
    if args.target in {"dagmanager", "all"}:
        targets.append("dagmanager")

    missing = [section for section in targets if section not in unified.present_sections]
    if missing:
        for section in missing:
            print(
                f"[qmtl] Configuration file '{cfg_path}' does not define the '{section}' section.",
                file=sys.stderr,
            )
        raise SystemExit(2)

    results: Dict[str, Dict[str, ValidationIssue]] = {}
    if "gateway" in targets:
        results["gateway"] = await validate_gateway_config(unified.gateway, offline=args.offline)
    if "dagmanager" in targets:
        results["dagmanager"] = await validate_dagmanager_config(
            unified.dagmanager, offline=args.offline
        )

    table = _render_table(results)
    if table:
        print(table)
    if args.json:
        if table:
            print()
        print(json.dumps(_issues_to_json(results), indent=2, sort_keys=True))

    if any(issue.severity == "error" for checks in results.values() for issue in checks.values()):
        raise SystemExit(1)
    return results


def run(argv: List[str] | None = None) -> None:
    argv = list(argv) if argv is not None else []

    if not argv or argv[0] in {"-h", "--help"}:
        _build_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]

    if cmd == "validate":
        parser = _build_validate_parser()
        args = parser.parse_args(rest)
        asyncio.run(_execute_validate(args))
        return

    _build_help_parser().print_help()
    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    run()
