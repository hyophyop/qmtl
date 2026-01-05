#!/usr/bin/env python3
"""Audit semantic drift between architecture docs and implementation.

This script performs lightweight, regex-based cross-checks between the Korean
canonical architecture docs under ``docs/ko/architecture`` and the codebase.

Checks (best-effort):
- Config keys referenced in docs exist in the corresponding dataclass configs.
- HTTP/WebSocket routes referenced in docs exist in FastAPI routers.
- Prometheus metric names referenced in docs exist in metric definitions.

The goal is to surface likely mismatches quickly; it is not a formal verifier.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    kind: str  # config_key_missing | route_missing | metric_missing
    doc: str
    line: int
    token: str
    context: str


_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_ROUTE_DECORATOR_RE = re.compile(
    r"""\b(?P<obj>router|app)\.(?P<verb>get|post|put|delete|patch|options|head|api_route)\(\s*["'](?P<path>/[^"']+)["']""",
    re.VERBOSE,
)
_ADD_API_ROUTE_RE = re.compile(
    r"""\badd_api_route\(\s*["'](?P<path>/[^"']+)["']""",
    re.VERBOSE,
)
_PROM_METRIC_RE = re.compile(
    r"""\b(?:Counter|Gauge|Histogram|Summary)\(\s*["'](?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)["']""",
    re.VERBOSE,
)
_HELPER_METRIC_CALL_RE = re.compile(
    r"""\b(?:_counter|_gauge|_histogram|_summary|get_or_create_counter|get_or_create_gauge|get_or_create_histogram|get_or_create_summary)\(\s*["'](?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)["']""",
    re.VERBOSE,
)
_METRIC_TOKEN_RE = re.compile(r"^[a-z_][a-z0-9_]*(?::[a-z_][a-z0-9_]*)?$")
_LIKELY_METRIC_HINTS: tuple[str, ...] = (
    "_total",
    "_seconds",
    "_ms",
    "_bucket",
    "_count",
    "_sum",
    "_ratio",
    "_latency",
    "_duration",
    "_requests",
    "_errors",
    "_failures",
    "_hits",
    "_misses",
    "_p95",
    "_p99",
)
_METRIC_PREFIXES: tuple[str, ...] = (
    "gateway_",
    "dagmanager_",
    "world_",
    "controlbus_",
    "seamless_",
    "nodeid_",
    "tagquery_",
    "rebalance_",
    "ws_",
    "history_",
    "artifact_",
    "gap_",
    "snapshot_",
    "warmup_",
    "orders_",
    "fills_",
)

_PRESET_REGISTER_RE = re.compile(
    r"""\bSeamlessPresetRegistry\.register\(\s*["'](?P<name>[^"']+)["']""",
    re.VERBOSE,
)


def _iter_md_files(base: Path) -> Iterable[Path]:
    yield from sorted(base.glob("*.md"))


def _parse_dataclass_fields(py_file: Path) -> dict[str, dict[str, str]]:
    """Return mapping of {ClassName: {field_name: annotation_string}}."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    classes: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(
            isinstance(dec, ast.Name) and dec.id == "dataclass"
            or isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
            for dec in node.decorator_list
        ):
            continue
        fields: dict[str, str] = {}
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            if not isinstance(stmt.target, ast.Name):
                continue
            name = stmt.target.id
            if name.startswith("_"):
                continue
            ann = stmt.annotation
            ann_src = ast.get_source_segment(py_file.read_text(encoding="utf-8"), ann)
            if ann_src is None:
                ann_src = "Any"
            fields[name] = ann_src.strip()
        classes[node.name] = fields
    return classes


def _strip_quotes(type_expr: str) -> str:
    type_expr = type_expr.strip()
    if (type_expr.startswith('"') and type_expr.endswith('"')) or (
        type_expr.startswith("'") and type_expr.endswith("'")
    ):
        return type_expr[1:-1]
    return type_expr


def _extract_primary_type(type_expr: str) -> str:
    """Best-effort to extract a dataclass-ish type from an annotation string."""
    t = _strip_quotes(type_expr)
    # Remove common wrappers.
    for token in ("Optional[", "list[", "dict[", "Mapping[", "Sequence[", "set["):
        if t.startswith(token):
            t = t[len(token) :]
            break
    # Handle unions (PEP604 "A | None") or typing "Union[A, B]"
    t = t.split("|", 1)[0].strip()
    if t.startswith("Union["):
        inner = t[len("Union[") :].rstrip("]")
        t = inner.split(",", 1)[0].strip()
    # Remove generics
    t = t.split("[", 1)[0].strip()
    # Remove module qualifiers
    t = t.rsplit(".", 1)[-1]
    return t


def _build_config_index(root: Path) -> tuple[Mapping[str, str], Mapping[str, dict[str, str]]]:
    """Return (root_key -> ClassName, ClassName -> {field->annotation})."""
    sources = [
        root / "qmtl" / "foundation" / "config.py",
        root / "qmtl" / "services" / "gateway" / "config.py",
        root / "qmtl" / "services" / "dagmanager" / "config.py",
        root / "qmtl" / "services" / "worldservice" / "config.py",
    ]
    class_fields: dict[str, dict[str, str]] = {}
    for src in sources:
        class_fields.update(_parse_dataclass_fields(src))

    roots: dict[str, str] = {
        "gateway": "GatewayConfig",
        "dagmanager": "DagManagerConfig",
        "worldservice": "WorldServiceConfig",
        "seamless": "SeamlessConfig",
        "connectors": "ConnectorsConfig",
        "telemetry": "TelemetryConfig",
        "cache": "CacheConfig",
        "runtime": "RuntimeConfig",
        "test": "TestConfig",
        "project": "ProjectConfig",
        "risk_hub": "RiskHubConfig",
    }
    return roots, class_fields


def _config_key_exists(key: str, roots: Mapping[str, str], class_fields: Mapping[str, dict[str, str]]) -> bool:
    parts = key.split(".")
    if len(parts) < 2:
        return True
    root = parts[0]
    cls = roots.get(root)
    if cls is None:
        return True
    current = cls
    for idx, part in enumerate(parts[1:], 1):
        fields = class_fields.get(current)
        if fields is None:
            return False
        ann = fields.get(part)
        if ann is None:
            return False
        if idx == len(parts) - 1:
            return True
        next_type = _extract_primary_type(ann)
        if next_type not in class_fields:
            return False
        current = next_type
    return True


def _collect_routes(root: Path) -> set[str]:
    routes: set[str] = set()
    for py in root.glob("qmtl/**/*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in _ROUTE_DECORATOR_RE.finditer(text):
            routes.add(m.group("path"))
        for m in _ADD_API_ROUTE_RE.finditer(text):
            routes.add(m.group("path"))
    return routes


def _collect_metrics(root: Path) -> set[str]:
    metrics: set[str] = set()
    for py in root.glob("qmtl/**/*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in _PROM_METRIC_RE.finditer(text):
            metrics.add(m.group("name"))
        for m in _HELPER_METRIC_CALL_RE.finditer(text):
            metrics.add(m.group("name"))
    return metrics


def _collect_seamless_presets(root: Path) -> set[str]:
    presets: set[str] = set()
    src = root / "qmtl" / "runtime" / "io" / "seamless_presets.py"
    if not src.exists():
        return presets
    text = src.read_text(encoding="utf-8", errors="ignore")
    for m in _PRESET_REGISTER_RE.finditer(text):
        presets.add(m.group("name"))
    return presets


def _extract_doc_tokens(md: Path) -> tuple[set[str], set[str], set[str], list[tuple[int, str]]]:
    """Return (config_keys, routes, metrics, lines)."""
    config_keys: set[str] = set()
    routes: set[str] = set()
    metrics: set[str] = set()
    lines: list[tuple[int, str]] = []
    for idx, line in enumerate(md.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        lines.append((idx, line))
        for m in _CODE_SPAN_RE.finditer(line):
            raw = m.group(1).strip()
            if not raw or " " in raw:
                continue

            # Split common "a/b" shorthand used in docs (e.g., gateway.x/gateway.y).
            parts = [raw]
            if (
                "/" in raw
                and raw.count("/") <= 2
                and not raw.startswith(("qmtl/", "docs/", "../", "./"))
                and "://" not in raw
            ):
                parts = [p.strip() for p in raw.split("/") if p.strip()]

            for token in parts:
                # Strip "=value" used in docs for emphasis (e.g., key=value).
                if "=" in token and token.count("=") == 1 and not token.startswith("http"):
                    token = token.split("=", 1)[0].strip()

                if token.startswith(("/", "ws://", "wss://", "http://", "https://")):
                    if token.startswith("/") and "*" not in token:
                        routes.add(token)
                    continue

                if "." in token and "/" not in token:
                    # likely config key, but keep filtered later by roots
                    segs = token.split(".")
                    if len(segs) >= 3 or "_" in token:
                        config_keys.add(token)
                    continue

                if (
                    _METRIC_TOKEN_RE.match(token)
                    and "_" in token
                    and not token.startswith("_")
                    and "." not in token
                    and "/" not in token
                    and (
                        token.startswith(_METRIC_PREFIXES)
                        or ":" in token
                        or token.endswith(("_total", "_bucket", "_count", "_sum"))
                    )
                    and (":" in token or any(hint in token for hint in _LIKELY_METRIC_HINTS))
                ):
                    metrics.add(token)
    return config_keys, routes, metrics, lines


def audit_architecture_semantics(
    *,
    root: Path = ROOT,
    docs_dir: Path | None = None,
) -> dict[str, object]:
    docs_dir = docs_dir or root / "docs" / "ko" / "architecture"
    roots, class_fields = _build_config_index(root)
    routes = _collect_routes(root)
    metrics = _collect_metrics(root)
    presets = _collect_seamless_presets(root)

    findings: list[Finding] = []
    summary: dict[str, int] = {"config_key_missing": 0, "route_missing": 0, "metric_missing": 0}

    for md in _iter_md_files(docs_dir):
        config_keys, doc_routes, doc_metrics, lines = _extract_doc_tokens(md)
        # Filter config keys to known roots only.
        config_keys = {k for k in config_keys if k.split(".", 1)[0] in roots}

        # Index lines for context lookups.
        line_text: dict[int, str] = {n: t for n, t in lines}

        def _record(kind: str, line_no: int, token: str) -> None:
            summary[kind] += 1
            findings.append(
                Finding(
                    kind=kind,
                    doc=str(md.relative_to(root)),
                    line=line_no,
                    token=token,
                    context=line_text.get(line_no, "").strip(),
                )
            )

        # Config keys.
        for key in sorted(config_keys):
            if _config_key_exists(key, roots, class_fields):
                continue
            if key in presets:
                continue
            # locate first mention line
            for line_no, txt in lines:
                if f"`{key}`" in txt:
                    _record("config_key_missing", line_no, key)
                    break

        # Routes.
        for path in sorted(doc_routes):
            # Normalize trailing slashes to reduce false positives.
            normalized = path.rstrip("/") or "/"
            if normalized in routes:
                continue
            for line_no, txt in lines:
                if f"`{path}`" in txt:
                    _record("route_missing", line_no, path)
                    break

        # Metrics.
        for name in sorted(doc_metrics):
            if name in metrics:
                continue
            for line_no, txt in lines:
                if f"`{name}`" in txt:
                    _record("metric_missing", line_no, name)
                    break

    payload = {
        "docs_dir": str(docs_dir.relative_to(root)) if docs_dir.is_relative_to(root) else str(docs_dir),
        "summary": summary,
        "findings": [f.__dict__ for f in findings],
        "notes": [
            "This report is heuristic. False positives are possible (examples, legacy notes, or planned-but-not-implemented features).",
            "Config key validation is based on dataclass field names in config modules.",
            "Route validation scans for FastAPI-style route decorators and add_api_route calls.",
            "Metric validation scans for prometheus_client Counter/Gauge/Histogram/Summary string literals.",
        ],
    }
    return payload


def _format_markdown(report: Mapping[str, object]) -> str:
    summary = report.get("summary", {})
    findings = report.get("findings", [])
    out: list[str] = []
    out.append("# Architecture semantic audit (ko)")
    out.append("")
    out.append(f"- docs_dir: `{report.get('docs_dir')}`")
    out.append(f"- config_key_missing: {summary.get('config_key_missing', 0)}")
    out.append(f"- route_missing: {summary.get('route_missing', 0)}")
    out.append(f"- metric_missing: {summary.get('metric_missing', 0)}")
    out.append("")
    out.append("## Findings")
    if not findings:
        out.append("")
        out.append("- (none)")
        return "\n".join(out) + "\n"
    out.append("")
    for item in findings:
        out.append(
            f"- {item['kind']}: `{item['token']}` — `{item['doc']}:{item['line']}`"
        )
        if item.get("context"):
            out.append(f"  - {item['context']}")
    out.append("")
    out.append("## Notes")
    out.append("")
    for note in report.get("notes", []):
        out.append(f"- {note}")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audit_architecture_semantics")
    parser.add_argument(
        "--docs-dir",
        default=str(ROOT / "docs" / "ko" / "architecture"),
        help="Docs directory to audit (default: docs/ko/architecture)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "md"),
        default="md",
        help="Output format",
    )
    parser.add_argument(
        "--write",
        default="",
        help="Write output to a file (in addition to stdout)",
    )
    args = parser.parse_args(argv)

    report = audit_architecture_semantics(docs_dir=Path(args.docs_dir))
    if args.format == "json":
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    else:
        text = _format_markdown(report)

    print(text, end="")
    if args.write:
        Path(args.write).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
