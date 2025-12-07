from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from qmtl.foundation.config import find_config_file, load_config
from qmtl.utils.i18n import _
from qmtl.foundation.config_validation import (
    ValidationIssue,
    validate_config_structure,
    validate_dagmanager_config,
    validate_gateway_config,
    validate_worldservice_config,
)
from qmtl.interfaces.config_templates import (
    available_profiles,
    write_template,
)

_STATUS_LABELS = {
    "ok": "OK",
    "warning": "WARN",
    "error": "ERROR",
}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl config", add_help=True)
    parser.description = textwrap.dedent(
        _(
            """
            Configuration utilities.

            Subcommands:
              validate  Check connectivity and readiness for Gateway and DAG Manager.
              generate  Scaffold configuration files from packaged templates.
            """
        )
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["validate", "generate"],
        help=_("Subcommand to run"),
    )
    return parser


def _build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl config validate")
    parser.add_argument(
        "--config",
        help=_("Path to configuration file (defaults to qmtl.yml in CWD)"),
    )
    parser.add_argument(
        "--target",
        choices=["schema", "gateway", "dagmanager", "worldservice", "all"],
        default="all",
        help=_("Limit validation to a specific service"),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=_("Skip network-dependent checks (assume services are offline)"),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=_("Emit validation report as JSON in addition to the table"),
    )
    return parser


def _build_generate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl config generate")
    profiles = sorted(available_profiles())
    parser.add_argument(
        "--profile",
        choices=profiles,
        default="dev",
        help=_("Configuration template profile to write (dev/prod; minimal/maximal kept as aliases)"),
    )
    parser.add_argument(
        "--output",
        default="qmtl.yml",
        help=_("Destination path for the generated configuration"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=_("Overwrite existing files"),
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
        yield _("  (no checks executed)")
        return
    width = max(len(name) for name in checks)
    for name, issue in checks.items():
        label = _STATUS_LABELS.get(issue.severity, issue.severity.upper())
        yield _("  {name}  {label:<5}  {hint}").format(name=name.ljust(width), label=label, hint=issue.hint)


def _render_table(results: Mapping[str, Mapping[str, ValidationIssue]]) -> str:
    lines: List[str] = []
    for target, checks in results.items():
        lines.append(_("{target}:").format(target=target))
        lines.extend(_format_checks(checks))
        lines.append("")
    return "\n".join(lines).strip()


async def _execute_validate(args: argparse.Namespace) -> Mapping[str, Mapping[str, ValidationIssue]]:
    cfg_path = args.config or find_config_file()
    if not cfg_path:
        print(_("[qmtl] Configuration file not found. Specify --config."), file=sys.stderr)
        raise SystemExit(2)

    unified = _load_or_exit(cfg_path)
    targets = _resolve_targets(args.target)
    _ensure_sections_present(cfg_path, targets, unified.present_sections)

    results = await _validate_targets(unified, targets, args.offline)
    _print_results(results, as_json=args.json)

    if _has_errors(results):
        raise SystemExit(1)
    return results


def _load_or_exit(cfg_path: str):
    try:
        return load_config(cfg_path)
    except FileNotFoundError:
        print(_("[qmtl] Configuration file '{path}' does not exist.").format(path=cfg_path), file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:  # pragma: no cover - defensive catch
        print(_("[qmtl] Failed to load configuration: {exc}").format(exc=exc), file=sys.stderr)
        raise SystemExit(2) from exc


def _resolve_targets(target: str) -> List[str]:
    targets: List[str] = []
    if target in {"gateway", "all"}:
        targets.append("gateway")
    if target in {"dagmanager", "all"}:
        targets.append("dagmanager")
    if target in {"worldservice", "all"}:
        targets.append("worldservice")
    return targets


def _ensure_sections_present(cfg_path: str, targets: List[str], present_sections: List[str]) -> None:
    missing = [section for section in targets if section not in present_sections]
    if not missing:
        return
    for section in missing:
        print(
            _("[qmtl] Configuration file '{path}' does not define the '{section}' section.").format(
                path=cfg_path, section=section
            ),
            file=sys.stderr,
        )
    raise SystemExit(2)


async def _validate_targets(unified, targets: List[str], offline: bool) -> Dict[str, Dict[str, ValidationIssue]]:
    results: Dict[str, Dict[str, ValidationIssue]] = {}
    results["schema"] = validate_config_structure(unified)
    if "gateway" in targets:
        results["gateway"] = await validate_gateway_config(
            unified.gateway, offline=offline, profile=unified.profile
        )
    if "dagmanager" in targets:
        results["dagmanager"] = await validate_dagmanager_config(
            unified.dagmanager, offline=offline, profile=unified.profile
        )
    if "worldservice" in targets:
        results["worldservice"] = validate_worldservice_config(
            unified.worldservice.server, profile=unified.profile
        )
    return results


def _print_results(results: Mapping[str, Mapping[str, ValidationIssue]], *, as_json: bool) -> None:
    table = _render_table(results)
    if table:
        print(table)
    if as_json:
        if table:
            print()
        print(json.dumps(_issues_to_json(results), indent=2, sort_keys=True))


def _has_errors(results: Mapping[str, Mapping[str, ValidationIssue]]) -> bool:
    return any(issue.severity == "error" for checks in results.values() for issue in checks.values())


def _execute_generate(args: argparse.Namespace) -> Path:
    output = Path(args.output)

    try:
        write_template(args.profile, output, force=args.force)
    except FileExistsError:
        print(
            _("[qmtl] Output file '{path}' already exists. Use --force to overwrite.").format(path=output),
            file=sys.stderr,
        )
        raise SystemExit(2)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        print(_("[qmtl] {exc}").format(exc=exc), file=sys.stderr)
        raise SystemExit(2)

    print(_("[qmtl] Wrote {profile} configuration template to {path}").format(profile=args.profile, path=output))
    return output


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

    if cmd == "generate":
        parser = _build_generate_parser()
        args = parser.parse_args(rest)
        _execute_generate(args)
        return

    _build_help_parser().print_help()
    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    run()
