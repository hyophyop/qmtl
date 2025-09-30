from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import shlex
import sys
import textwrap
from typing import Dict, Iterable, List, Mapping, Sequence

from qmtl.foundation.config import find_config_file, load_config
from qmtl.foundation.config_env import (
    ConfigEnvVar,
    collect_managed_keys,
    is_secret_key,
    mask_value,
    unified_to_env,
)
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
          env       Environment variable helpers for Gateway and DAG Manager config.
        """
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["validate", "env"],
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


def _build_env_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl config env")
    subparsers = parser.add_subparsers(dest="subcmd")
    subparsers.required = True

    export = subparsers.add_parser(
        "export",
        help="Render environment assignments for the active configuration",
    )
    export.add_argument(
        "--config",
        help="Path to configuration file (defaults to qmtl.yml in CWD)",
    )
    export.add_argument(
        "--shell",
        choices=["posix", "powershell"],
        default="posix",
        help="Output format for the generated script",
    )
    export.add_argument(
        "--include-secret",
        action="store_true",
        help="Include secrets in the output instead of omitting them",
    )

    show = subparsers.add_parser(
        "show", help="Show relevant QMTL environment variables"
    )
    show.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON payload in addition to the table",
    )
    show.add_argument(
        "--include-secret",
        action="store_true",
        help="Show secret values without masking",
    )

    clear = subparsers.add_parser(
        "clear",
        help="Generate commands to clear QMTL configuration environment variables",
    )
    clear.add_argument(
        "--shell",
        choices=["posix", "powershell"],
        default="posix",
        help="Output format for the generated script",
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


def _comment(shell: str, text: str) -> str:
    return f"# {text}" if text else ""


def _quote_value(shell: str, value: str) -> str:
    if shell == "posix":
        return shlex.quote(value)
    escaped = value.replace("\"", '""')
    return f'"{escaped}"'


def _format_assignment(shell: str, key: str, value: str) -> str:
    if shell == "posix":
        return f"export {key}={_quote_value(shell, value)}"
    return f"$Env:{key}={_quote_value(shell, value)}"


def _format_clear(shell: str, key: str) -> str:
    if shell == "posix":
        return f"unset {key}"
    return f"Remove-Item Env:{key} -ErrorAction SilentlyContinue"


def _render_env_table(entries: Sequence[Dict[str, object]]) -> str:
    if not entries:
        return "(no QMTL config environment variables found)"

    width = max(len("KEY"), *(len(entry["key"]) for entry in entries))
    lines: List[str] = []
    lines.append(f"{'KEY'.ljust(width)}  VALUE")
    lines.append(f"{'-' * width}  {'-' * 5}")
    for entry in entries:
        value = entry.get("value", "")
        lines.append(f"{entry['key'].ljust(width)}  {value}")
    return "\n".join(lines)


def _execute_env_export(args: argparse.Namespace) -> List[ConfigEnvVar]:
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

    env_vars = unified_to_env(unified)
    secrets = [var for var in env_vars if var.secret]
    include_secret = getattr(args, "include_secret", False)
    shell = getattr(args, "shell", "posix")

    if not include_secret:
        env_vars = [var for var in env_vars if not var.secret]

    cfg_abs = os.path.abspath(cfg_path)
    timestamp = (
        datetime.datetime.now(datetime.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    metadata = {
        "generated_at": timestamp,
        "include_secret": include_secret,
        "shell": shell,
        "secrets_omitted": bool(secrets and not include_secret),
        "variables": len(env_vars),
    }

    lines: List[str] = []
    lines.append(_format_assignment(shell, "QMTL_CONFIG_SOURCE", cfg_abs))
    lines.append(
        _format_assignment(
            shell,
            "QMTL_CONFIG_EXPORT",
            json.dumps(metadata, sort_keys=True),
        )
    )

    if secrets and not include_secret:
        skipped_keys = ", ".join(var.key for var in secrets)
        lines.append(
            _comment(
                shell,
                f"Secrets omitted ({skipped_keys}). Re-run with --include-secret to include them.",
            )
        )

    for var in env_vars:
        lines.append(_format_assignment(shell, var.key, var.value))

    print("\n".join(line for line in lines if line))
    return env_vars


def _execute_env_show(args: argparse.Namespace) -> List[Dict[str, object]]:
    include_secret = getattr(args, "include_secret", False)
    env_keys = collect_managed_keys(os.environ)
    entries: List[Dict[str, object]] = []
    for key in env_keys:
        raw = os.environ.get(key)
        if raw is None:
            continue
        secret = is_secret_key(key)
        value = raw if include_secret or not secret else mask_value(raw)
        entries.append(
            {
                "key": key,
                "value": value,
                "secret": secret,
                "masked": secret and not include_secret,
            }
        )

    table = _render_env_table(entries)
    print(table)
    if getattr(args, "json", False):
        if entries:
            print()
        print(json.dumps(entries, indent=2, sort_keys=True))

    return entries


def _execute_env_clear(args: argparse.Namespace) -> List[str]:
    shell = getattr(args, "shell", "posix")
    env_keys = collect_managed_keys(os.environ, include_missing_meta=True)
    if not env_keys:
        msg = _comment(shell, "No QMTL config environment variables found.")
        if msg:
            print(msg)
        return []

    lines = [_format_clear(shell, key) for key in env_keys]
    print("\n".join(lines))
    return env_keys


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
    if cmd == "env":
        parser = _build_env_parser()
        args = parser.parse_args(rest)
        if args.subcmd == "export":
            _execute_env_export(args)
            return
        if args.subcmd == "show":
            _execute_env_show(args)
            return
        if args.subcmd == "clear":
            _execute_env_clear(args)
            return

    _build_help_parser().print_help()
    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    run()
