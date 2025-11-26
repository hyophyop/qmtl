"""QMTL v2.0 CLI - Simplified command-line interface.

Primary commands:
  submit   Submit a strategy for evaluation and activation
  status   Check status of submitted strategies
  world    World management commands
  init     Initialize a new project

Legacy commands show deprecation messages with migration hints.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, List, Mapping, Sequence, cast

import httpx
from httpx import _types as httpx_types

from qmtl.utils.i18n import set_language
from qmtl.utils.i18n import _ as _t  # Alias to avoid shadowing in loops

DEFAULT_GATEWAY_URL = "http://localhost:8000"


def _gateway_url() -> str:
    return os.environ.get("QMTL_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")


QueryParamValue = str | int | float | bool | None
QueryParams = Mapping[str, QueryParamValue] | Sequence[tuple[str, QueryParamValue]]


def _normalize_params(params: dict[str, object] | None) -> QueryParams | None:
    """Coerce loose dict params into httpx-friendly query params."""
    if params is None:
        return None
    normalized: dict[str, QueryParamValue] = {}
    for key, value in params.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized


def _http_get(path: str, params: dict[str, object] | None = None) -> tuple[int, object | None]:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{_gateway_url()}{path}",
                params=cast(httpx_types.QueryParamTypes | None, _normalize_params(params)),
            )
            payload = None
            try:
                payload = resp.json()
            except Exception:
                payload = None
            return resp.status_code, payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def _http_post(path: str, json_payload: object) -> tuple[int, object | None]:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(f"{_gateway_url()}{path}", json=json_payload)
            payload = None
            try:
                payload = resp.json()
            except Exception:
                payload = None
            return resp.status_code, payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def _http_delete(path: str) -> tuple[int, object | None]:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.delete(f"{_gateway_url()}{path}")
            payload = None
            try:
                payload = resp.json()
            except Exception:
                payload = None
            return resp.status_code, payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def _build_top_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtl",
        add_help=True,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.description = textwrap.dedent(_t("""
        QMTL v2.0 - Simplified Strategy Submission

        Commands:
          submit    Submit a strategy for evaluation and activation
          status    Check status of submitted strategies  
          world     World management (list, create, info)
          init      Initialize a new project

        Examples:
          qmtl submit my_strategy.py
          qmtl submit my_strategy.py --world prod --mode live
          qmtl status
          qmtl world list
          qmtl init my_project

        Environment Variables:
          QMTL_GATEWAY_URL     Gateway URL (default: http://localhost:8000)
          QMTL_DEFAULT_WORLD   Default world (default: __default__)
          
        For service administration, see: qmtl --help-admin
    """)).strip()
    return parser


def _build_admin_help() -> str:
    """Build help text for admin/operator commands."""
    return textwrap.dedent(_t("""
        QMTL v2.0 - Administration Commands

        These commands are for operators and developers managing QMTL services.
        Regular users should use 'qmtl submit' to submit strategies.

        Service Commands:
          gw, gateway       Start the Gateway HTTP server
          dagmanager-server Start the DAG Manager gRPC server

        Developer Tools:
          taglint           Lint and fix TAGS dictionaries in strategy files

        Examples:
          qmtl gw --config qmtl.yml
          qmtl dagmanager-server --port 50051
          qmtl taglint my_strategy.py

        For user commands, see: qmtl --help
    """)).strip()


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
    overrides: dict[str, float] = {}
    for raw in args.preset_override or []:
        if "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        k = k.strip()
        try:
            overrides[k] = float(v)
        except Exception:
            continue
    
    # Load strategy
    strategy_cls = _load_strategy(args.strategy)
    if strategy_cls is None:
        print(_t("Error: Could not load strategy from '{}'").format(args.strategy), file=sys.stderr)
        return 1
    
    # Submit
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
        
        # Display result
        print(_t("\n📊 Strategy Submission Result"))
        print("=" * 40)
        print(f"Strategy ID: {result.strategy_id}")
        print(f"Status:      {result.status}")
        print(f"World:       {result.world}")
        print(f"Mode:        {result.mode.value}")
        
        if result.status == "active":
            print(_t("\n✅ Strategy activated successfully!"))
            if result.contribution is not None:
                print(f"Contribution: {result.contribution:.2%}")
            if result.weight is not None:
                print(f"Weight:       {result.weight:.2%}")
            if result.rank is not None:
                print(f"Rank:         #{result.rank}")
        elif result.status == "rejected":
            print(_t("\n❌ Strategy rejected"))
            if result.rejection_reason:
                print(f"Reason: {result.rejection_reason}")
            if result.improvement_hints:
                print(_t("\n💡 Improvement hints:"))
                for hint in result.improvement_hints:
                    print(f"  - {hint}")
        else:
            print(f"\n⏳ Status: {result.status}")
        
        return 0 if result.status != "rejected" else 1
        
    except Exception as e:
        print(_t("Error: {}").format(str(e)), file=sys.stderr)
        return 1


def cmd_status(argv: List[str]) -> int:
    """Check status of submitted strategies."""
    parser = argparse.ArgumentParser(
        prog="qmtl status",
        description=_t("Check status of submitted strategies"),
    )
    parser.add_argument("--strategy", "-s", default=None, help=_t("Strategy ID to inspect"))
    parser.add_argument("--world", "-w", default=None, help=_t("Filter by world (list mode)"))
    parser.add_argument("--status", default=None, help=_t("Filter by status (list mode)"))
    parser.add_argument("--limit", "-n", type=int, default=20, help=_t("Max items to list"))
    parser.add_argument("--json", action="store_true", help=_t("Output raw JSON"))
    parser.add_argument("--with-world-info", action="store_true", help=_t("Include world policy summary (single strategy)"))
    
    args = parser.parse_args(argv)

    # Single-strategy path
    if args.strategy:
        status_code, payload = _http_get(f"/strategies/{args.strategy}/status")
        if status_code == 404:
            print(_t("Strategy '{}' not found").format(args.strategy), file=sys.stderr)
            return 1
        if status_code >= 400 or status_code == 0:
            error = None
            if isinstance(payload, dict):
                error = payload.get("detail") or payload.get("error")
            print(_t("Error fetching status: {}").format(error or status_code), file=sys.stderr)
            return 1

        if args.json:
            print(payload if payload is not None else "{}")
            return 0

        status_val = None
        world = None
        mode = None
        if isinstance(payload, dict):
            status_val = payload.get("status")
            world = payload.get("world") or payload.get("world_id")
            mode = payload.get("mode")

        print(_t("📊 Strategy Status"))
        print("=" * 40)
        print(f"Strategy: {args.strategy}")
        print(f"Status:   {status_val or 'unknown'}")
        if world:
            print(f"World:    {world}")
        if mode:
            print(f"Mode:     {mode}")
        if args.with_world_info and world:
            ws_code, ws_payload = _http_get(f"/worlds/{world}/describe")
            if ws_code == 200 and isinstance(ws_payload, dict):
                human = ws_payload.get("policy_human") or "n/a"
                preset = ws_payload.get("policy_preset") or "n/a"
                version = ws_payload.get("default_policy_version") or "n/a"
                print(f"Policy:   preset={preset}, version={version}, {human}")
        print()
        print(_t("Gateway: {}").format(_gateway_url()))
        return 0

    # List mode (best-effort; requires Gateway support)
    params: dict[str, object] = {}
    if args.world:
        params["world"] = args.world
    if args.status:
        params["status"] = args.status
    if args.limit:
        params["limit"] = args.limit

    status_code, payload = _http_get("/strategies", params=params or None)
    if status_code == 404:
        print(_t("Gateway does not support listing strategies (404)"), file=sys.stderr)
        return 1
    if status_code >= 400 or status_code == 0:
        err = None
        if isinstance(payload, dict):
            err = payload.get("detail") or payload.get("error")
        print(_t("Error fetching strategies: {}").format(err or status_code), file=sys.stderr)
        return 1

    if args.json:
        print(payload if payload is not None else "[]")
        return 0

    strategies = payload if isinstance(payload, list) else []
    print(_t("📊 Strategy Status List"))
    print("=" * 60)
    if not strategies:
        print(_t("No strategies found"))
        return 0

    for item in strategies[: args.limit]:
        if not isinstance(item, dict):
            print(item)
            continue
        sid = item.get("id") or item.get("strategy_id") or "<unknown>"
        status_val = item.get("status") or item.get("state") or "unknown"
        world = item.get("world") or item.get("world_id") or "-"
        mode = item.get("mode") or "-"
        print(f"- {sid} | status={status_val} | world={world} | mode={mode}")
    return 0


def cmd_world(argv: List[str]) -> int:
    """World management commands."""
    parser = argparse.ArgumentParser(
        prog="qmtl world",
        description=_t("World management commands"),
    )
    parser.add_argument(
        "action",
        choices=["list", "create", "info", "delete"],
        help=_t("Action to perform"),
    )
    parser.add_argument(
        "name",
        nargs="?",
        help=_t("World name (for create/info/delete)"),
    )
    parser.add_argument(
        "--policy", "-p",
        choices=["sandbox", "conservative", "moderate", "aggressive"],
        default="conservative",
        help=_t("Policy preset for new world (default: conservative)"),
    )
    parser.add_argument(
        "--preset-mode",
        choices=["shared", "clone", "extend"],
        default=None,
        help=_t("How to apply preset policy to the world (metadata only)"),
    )
    parser.add_argument(
        "--preset-version",
        default=None,
        help=_t("Optional preset version identifier for the world"),
    )
    parser.add_argument(
        "--preset-override",
        action="append",
        default=[],
        help=_t("Override preset thresholds (key=value, e.g., max_drawdown.max=0.15)"),
    )
    
    args = parser.parse_args(argv)
    
    if args.action == "list":
        status_code, payload = _http_get("/worlds")
        if status_code >= 400 or status_code == 0:
            err = payload.get("error") if isinstance(payload, dict) else status_code
            print(_t("Error fetching worlds: {}").format(err), file=sys.stderr)
            return 1
        worlds = payload if isinstance(payload, list) else []
        print(_t("🌍 Available Worlds"))
        print("=" * 40)
        if not worlds:
            print(_t("No worlds found"))
        else:
            for w in worlds:
                wid = w.get("id") if isinstance(w, dict) else str(w)
                name = w.get("name") if isinstance(w, dict) else ""
                if name:
                    print(f"- {wid} ({name})")
                else:
                    print(f"- {wid}")
        return 0
    
    if args.action in ("create", "info", "delete") and not args.name:
        print(_t("Error: World name required for {}").format(args.action), file=sys.stderr)
        return 1
    
    if args.action == "create":
        overrides: dict[str, float] = {}
        for raw in args.preset_override or []:
            if "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            k = k.strip()
            try:
                overrides[k] = float(v)
            except Exception:
                continue

        payload = {"id": args.name, "name": args.name}
        status_code, resp = _http_post("/worlds", payload)
        if status_code >= 400 or status_code == 0:
            err = resp.get("detail") if isinstance(resp, dict) else status_code
            print(_t("Error creating world: {}").format(err), file=sys.stderr)
            return 1
        # apply preset policy
        status_code, policy_resp = _http_post(
            f"/worlds/{args.name}/policies",
            {
                "preset": args.policy,
                "preset_mode": args.preset_mode,
                "preset_version": args.preset_version,
                "preset_overrides": overrides or None,
            },
        )
        if status_code >= 400 or status_code == 0:
            err = policy_resp.get("detail") if isinstance(policy_resp, dict) else status_code
            print(_t("World created, but failed to apply policy: {}").format(err), file=sys.stderr)
            return 1
        print(_t("World '{}' created with policy preset '{}'").format(args.name, args.policy))
        return 0

    if args.action == "info":
        status_code, resp = _http_get(f"/worlds/{args.name}/describe")
        if status_code == 404:
            print(_t("World '{}' not found").format(args.name), file=sys.stderr)
            return 1
        if status_code >= 400 or status_code == 0:
            err = resp.get("detail") if isinstance(resp, dict) else status_code
            print(_t("Error fetching world info: {}").format(err), file=sys.stderr)
            return 1
        print(_t("🌍 World Info"))
        print("=" * 40)
        if isinstance(resp, dict):
            print(f"id: {resp.get('id')}")
            print(f"name: {resp.get('name')}")
            print(f"default_policy_version: {resp.get('default_policy_version')}")
            print(f"policy_preset: {resp.get('policy_preset') or 'n/a'}")
            print(f"policy_human: {resp.get('policy_human') or 'n/a'}")
        else:
            print(resp)
        return 0

    if args.action == "delete":
        status_code, resp = _http_delete(f"/worlds/{args.name}")
        if status_code == 404:
            print(_t("World '{}' not found").format(args.name), file=sys.stderr)
            return 1
        if status_code >= 400 or status_code == 0:
            err = resp.get("detail") if isinstance(resp, dict) else status_code
            print(_t("Error deleting world: {}").format(err), file=sys.stderr)
            return 1
        print(_t("World '{}' deleted").format(args.name))
        return 0

    # Should never reach here
    print(_t("Unknown action"))
    return 1


def cmd_init(argv: List[str]) -> int:
    """Initialize a new project."""
    parser = argparse.ArgumentParser(
        prog="qmtl init",
        description=_t("Initialize a new QMTL project"),
    )
    parser.add_argument(
        "path",
        help=_t("Project directory path"),
    )
    parser.add_argument(
        "--preset",
        choices=["minimal", "full"],
        default="minimal",
        help=_t("Project template preset (default: minimal)"),
    )
    
    args = parser.parse_args(argv)
    
    project_path = Path(args.path)
    
    if project_path.exists() and any(project_path.iterdir()):
        print(_t("Error: Directory '{}' already exists and is not empty").format(args.path), file=sys.stderr)
        return 1
    
    # Create project structure
    project_path.mkdir(parents=True, exist_ok=True)
    
    # Create minimal strategy file
    strategy_content = '''"""Example QMTL Strategy.

This is a minimal strategy template. Customize the setup() method
to define your strategy logic.
"""

from qmtl.runtime.sdk import Strategy, StreamInput, ProcessingNode, Runner


class MyStrategy(Strategy):
    """A simple example strategy."""
    
    def setup(self):
        # Define input stream
        price = StreamInput(interval="1m", period=30)
        
        # Define processing logic
        def compute(view):
            # Your strategy logic here
            return view
        
        signal = ProcessingNode(
            input=price,
            compute_fn=compute,
            name="signal",
        )
        
        self.add_nodes([price, signal])


if __name__ == "__main__":
    # Submit strategy for evaluation
    result = Runner.submit(MyStrategy)
    print(f"Status: {result.status}")
'''
    
    (project_path / "strategy.py").write_text(strategy_content)
    
    # Create .env file template
    env_content = '''# QMTL Configuration
# Uncomment and set these values for your environment

# Gateway URL (default: http://localhost:8000)
# QMTL_GATEWAY_URL=http://localhost:8000

# Default world (default: __default__)
# QMTL_DEFAULT_WORLD=__default__
'''
    (project_path / ".env.example").write_text(env_content)
    
    print(_t("✅ Project initialized at '{}'").format(args.path))
    print()
    print(_t("Next steps:"))
    print(f"  1. cd {args.path}")
    print("  2. Edit strategy.py with your strategy logic")
    print("  3. qmtl submit strategy.py")
    
    return 0


def cmd_version(argv: List[str]) -> int:
    """Show version information."""
    try:
        from qmtl import __version__
        version = __version__
    except ImportError:
        version = "unknown"
    
    print(f"QMTL version {version}")
    return 0


CommandHandler = Callable[[List[str]], int]


def _command_tables(admin: bool = False) -> tuple[dict[str, CommandHandler], dict[str, str]]:
    """Return (commands, legacy) tables; admin includes operator commands."""
    commands = {
        "submit": cmd_submit,
        "status": cmd_status,
        "world": cmd_world,
        "init": cmd_init,
        "version": cmd_version,
    }
    legacy = {
        "service": "Use 'qmtl submit' for strategy execution, 'qmtl --admin gw' for gateway",
        "tools": "Tools integrated into main commands. Use 'qmtl submit' instead",
        "project": "Use 'qmtl init' for project creation",
        "config": "Configuration simplified - use environment variables",
        "run": "Use 'qmtl submit' instead",
        "offline": "Use 'qmtl submit --mode backtest' instead",
    }
    if admin:
        commands = {
            **commands,
            "gw": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "gateway": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "dagmanager-server": lambda argv: int(import_module("qmtl.interfaces.cli.dagmanager").run(argv) or 0),
            "taglint": lambda argv: int(import_module("qmtl.interfaces.cli.taglint").run(argv) or 0),
        }
    else:
        commands = {
            **commands,
            "gw": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "gateway": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "dagmanager-server": lambda argv: int(import_module("qmtl.interfaces.cli.dagmanager").run(argv) or 0),
        }
    return cast(tuple[dict[str, CommandHandler], dict[str, str]], (commands, legacy))


# Export command registries for test/inspection without invoking argument parsing
_ALL_COMMANDS, LEGACY_COMMANDS = _command_tables(admin=False)
COMMANDS: dict[str, CommandHandler] = {
    "submit": cmd_submit,
    "status": cmd_status,
    "world": cmd_world,
    "init": cmd_init,
    "version": cmd_version,
}
_ADMIN_COMMANDS_FULL, _ = _command_tables(admin=True)
ADMIN_COMMANDS = {k: v for k, v in _ADMIN_COMMANDS_FULL.items() if k not in COMMANDS}


def _extract_lang(argv: List[str]) -> tuple[List[str], str | None]:
    """Extract --lang/-L from argv; return (rest, lang)."""
    rest: List[str] = []
    lang: str | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--lang="):
            lang = tok.split("=", 1)[1]
            i += 1
            continue
        if tok == "--lang" or tok == "-L":
            if i + 1 < len(argv):
                lang = argv[i + 1]
                i += 2
                continue
            i += 1
            continue
        rest.append(tok)
        i += 1
    return rest, lang


def _load_strategy(strategy_ref: str):
    """Load strategy class from file path or module:class reference."""
    import importlib.util
    
    # Check if it's a file path
    if strategy_ref.endswith(".py") or os.path.exists(strategy_ref):
        path = Path(strategy_ref)
        if not path.exists():
            return None
        
        # Load module from file
        spec = importlib.util.spec_from_file_location("strategy_module", path)
        if spec is None or spec.loader is None:
            return None
        
        module = importlib.util.module_from_spec(spec)
        sys.modules["strategy_module"] = module
        spec.loader.exec_module(module)
        
        # Find Strategy subclass
        from qmtl.runtime.sdk import Strategy
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                return obj
        
        return None
    
    # Parse module:class format
    if ":" in strategy_ref:
        module_path, class_name = strategy_ref.rsplit(":", 1)
    else:
        # Assume it's a module path with the class being the last part
        parts = strategy_ref.rsplit(".", 1)
        if len(parts) == 2:
            module_path, class_name = parts
        else:
            return None
    
    try:
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError):
        return None


def main(argv: List[str] | None = None) -> int:
    """Main CLI entry point."""
    argv = list(argv) if argv is not None else sys.argv[1:]

    # Extract language option
    argv, lang = _extract_lang(argv)
    set_language(lang)
    
    # No args or help → show help
    if not argv or argv[0] in {"-h", "--help"}:
        _build_top_help_parser().print_help()
        return 0

    # Admin help
    if argv[0] == "--help-admin":
        print(_build_admin_help())
        return 0
    
    admin_mode = False
    if argv and argv[0] == "--admin":
        admin_mode = True
        argv = argv[1:]

    cmd = argv[0] if argv else None
    rest = argv[1:] if len(argv) > 1 else []

    commands, legacy = _command_tables(admin=admin_mode)

    # Check for legacy commands
    if cmd in legacy:
        print(_t("⚠️  Command '{}' has been removed in QMTL v2.0").format(cmd), file=sys.stderr)
        print(_t("   {}").format(legacy[cmd]), file=sys.stderr)
        print(_t("\n   See https://qmtl.readthedocs.io/migrate/v2 for migration guide."), file=sys.stderr)
        return 2

    # Dispatch to command
    if cmd in commands:
        try:
            return commands[cmd](rest)
        except KeyboardInterrupt:
            print(_t("\nInterrupted"), file=sys.stderr)
            return 130
        except Exception as e:
            print(_t("Error: {}").format(str(e)), file=sys.stderr)
            return 1
    
    # Unknown command
    print(_t("Error: Unknown command '{}'").format(cmd), file=sys.stderr)
    hint = "Run 'qmtl --help' for user commands."
    if not admin_mode:
        hint += " Use 'qmtl --admin --help' for operator commands."
    print(_t(hint), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
