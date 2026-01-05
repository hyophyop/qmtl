#!/usr/bin/env python3
"""Audit contract-level drift between architecture docs and implementation.

This extends ``scripts/audit_architecture_semantics.py`` with more "meaning-level"
checks for:
- Error codes referenced in docs (e.g. ``E_NODE_ID_MISMATCH``) exist in code.
- WorldService Pydantic model field names + requiredness mentioned in docs match the
  actual schemas in ``qmtl/services/worldservice/schemas.py``.
- HTTP status-code tables in docs match the success status codes configured on the
  corresponding FastAPI routes.

The audit is best-effort and intentionally heuristic; it aims to catch likely drift
quickly without requiring heavyweight parsing or runtime imports.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    kind: str  # error_code_missing | schema_field_missing | schema_required_mismatch | status_table_mismatch | doc_status_not_in_code
    doc: str
    line: int
    token: str
    context: str


_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_ERROR_CODE_RE = re.compile(r"\bE_[A-Z0-9_]+\b")
_HTTP_STATUS_RE = re.compile(r"\b([1-5]\d{2})\b")
_ENDPOINT_LINE_RE = re.compile(r"^\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[^ \t]+)")
def _looks_like_http_status_table_header(line: str) -> bool:
    # Some docs contain non-breaking spaces; avoid relying on `\s` matching.
    text = line.strip()
    return text.startswith("|") and ("HTTP" in text) and ("Status" in text)

_STATUS_NAME_TO_INT: Mapping[str, int] = {
    "HTTP_200_OK": 200,
    "HTTP_201_CREATED": 201,
    "HTTP_202_ACCEPTED": 202,
    "HTTP_204_NO_CONTENT": 204,
    "HTTP_400_BAD_REQUEST": 400,
    "HTTP_401_UNAUTHORIZED": 401,
    "HTTP_403_FORBIDDEN": 403,
    "HTTP_404_NOT_FOUND": 404,
    "HTTP_409_CONFLICT": 409,
    "HTTP_422_UNPROCESSABLE_ENTITY": 422,
    "HTTP_429_TOO_MANY_REQUESTS": 429,
    "HTTP_500_INTERNAL_SERVER_ERROR": 500,
    "HTTP_501_NOT_IMPLEMENTED": 501,
    "HTTP_502_BAD_GATEWAY": 502,
    "HTTP_503_SERVICE_UNAVAILABLE": 503,
}


def _iter_md_files(base: Path) -> Iterable[Path]:
    yield from sorted(base.glob("*.md"))


def _iter_py_files(base: Path) -> Iterable[Path]:
    yield from sorted(base.glob("**/*.py"))


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _to_int_status(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "status":
            return _STATUS_NAME_TO_INT.get(node.attr)
    return None


def _extract_http_exception_statuses(tree: ast.AST) -> set[int]:
    statuses: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "HTTPException":
            pass
        elif isinstance(fn, ast.Attribute) and fn.attr == "HTTPException":
            pass
        else:
            continue
        for kw in node.keywords:
            if kw.arg != "status_code":
                continue
            resolved = _to_int_status(kw.value)
            if resolved is not None:
                statuses.add(resolved)
    return statuses


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    success_status: int
    file: Path
    handler_name: str


def _collect_fastapi_routes(root: Path) -> dict[tuple[str, str], RouteInfo]:
    """Return mapping {(METHOD, /path): RouteInfo} for known FastAPI routers/apps."""

    route_files: list[Path] = []
    route_files.extend((root / "qmtl" / "services").glob("**/routers/*.py"))
    route_files.extend((root / "qmtl" / "services" / "gateway" / "routes").glob("*.py"))
    route_files.append(root / "qmtl" / "services" / "dagmanager" / "api.py")

    routes: dict[tuple[str, str], RouteInfo] = {}
    for py in sorted({p for p in route_files if p.exists()}):
        text = _safe_read_text(py)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                if not isinstance(dec.func, ast.Attribute):
                    continue
                verb = dec.func.attr.lower()
                if verb not in {
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                    "api_route",
                }:
                    continue
                if not dec.args or not isinstance(dec.args[0], ast.Constant):
                    continue
                if not isinstance(dec.args[0].value, str):
                    continue
                path = str(dec.args[0].value)

                # Success status code: default to 200 unless explicitly configured.
                success_status: int = 200
                for kw in dec.keywords:
                    if kw.arg == "status_code":
                        resolved = _to_int_status(kw.value)
                        if resolved is not None:
                            success_status = resolved
                        break

                method = verb.upper() if verb != "api_route" else "ANY"
                routes[(method, path)] = RouteInfo(
                    method=method,
                    path=path,
                    success_status=success_status,
                    file=py,
                    handler_name=node.name,
                )
    return routes


def _collect_error_codes_in_code(root: Path) -> set[str]:
    codes: set[str] = set()
    for py in _iter_py_files(root / "qmtl"):
        text = _safe_read_text(py)
        codes.update(_ERROR_CODE_RE.findall(text))
    return codes


def _collect_error_code_findings(docs_dir: Path, *, code_codes: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for md in _iter_md_files(docs_dir):
        lines = _safe_read_text(md).splitlines()
        for idx, line in enumerate(lines, 1):
            for code in _ERROR_CODE_RE.findall(line):
                if code in code_codes:
                    continue
                findings.append(
                    Finding(
                        kind="error_code_missing",
                        doc=str(md.relative_to(ROOT)),
                        line=idx,
                        token=code,
                        context=line.strip(),
                    )
                )
    return findings


@dataclass(frozen=True)
class ModelField:
    required: bool


def _field_required_from_value(value: ast.AST | None) -> bool:
    if value is None:
        return True
    if isinstance(value, ast.Constant) and value.value is Ellipsis:
        return True
    if isinstance(value, ast.Call):
        # pydantic Field(...), Field(default=...), Field(default_factory=...)
        if isinstance(value.func, ast.Name) and value.func.id == "Field":
            if value.args and isinstance(value.args[0], ast.Constant) and value.args[0].value is Ellipsis:
                return True
            for kw in value.keywords:
                if kw.arg == "default":
                    if isinstance(kw.value, ast.Constant) and kw.value.value is Ellipsis:
                        return True
                    return False
                if kw.arg == "default_factory":
                    return False
            return False
    return False


def _parse_worldservice_schema_fields(py_file: Path) -> dict[str, dict[str, ModelField]]:
    """Return {ModelName: {field_name: ModelField(required=...)}} for BaseModel classes."""
    text = _safe_read_text(py_file)
    tree = ast.parse(text)
    out: dict[str, dict[str, ModelField]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_basemodel = any(
            isinstance(base, ast.Name) and base.id == "BaseModel"
            or isinstance(base, ast.Attribute) and base.attr == "BaseModel"
            for base in node.bases
        )
        if not is_basemodel:
            continue
        fields: dict[str, ModelField] = {}
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            if not isinstance(stmt.target, ast.Name):
                continue
            name = stmt.target.id
            if name.startswith("_"):
                continue
            required = _field_required_from_value(stmt.value)
            fields[name] = ModelField(required=required)
        out[node.name] = fields
    return out


def _normalize_field_token(token: str) -> str:
    token = token.strip()
    token = token.split("{", 1)[0]
    token = token.split("[", 1)[0]
    token = token.split("(", 1)[0]
    token = token.rstrip("[]")
    return token.strip()


def _extract_doc_fields(text: str) -> list[str]:
    raw = _CODE_SPAN_RE.findall(text)
    return [_normalize_field_token(tok) for tok in raw if tok.strip()]


def _extract_required_doc_fields(line: str) -> list[str]:
    if "필수 필드" not in line and "required field" not in line.lower():
        return []
    # Extract required fields up to the optional marker (if present).
    start = line.find("필수 필드")
    if start < 0:
        start = line.lower().find("required field")
    snippet = line[start:] if start >= 0 else line
    # Stop before optional marker to avoid mixing optional fields into required list.
    lowered = snippet.lower()
    for marker in ("선택적으로", "optional"):
        pos = lowered.find(marker)
        if pos >= 0:
            snippet = snippet[:pos]
            break
    return _extract_doc_fields(snippet)


def _extract_optional_doc_fields(line: str) -> list[str]:
    markers = ("선택적으로", "optional")
    lowered = line.lower()
    start = -1
    for marker in markers:
        pos = lowered.find(marker)
        if pos >= 0:
            start = pos
            break
    if start < 0:
        return []
    return _extract_doc_fields(line[start:])


def _schema_field_findings_for_worldservice_doc(
    doc_path: Path,
    schema_fields: Mapping[str, Mapping[str, ModelField]],
) -> list[Finding]:
    """Validate field names + requiredness claims in worldservice.md."""
    findings: list[Finding] = []
    lines = _safe_read_text(doc_path).splitlines()

    # Lines link to Pydantic models like: **입력 스키마:** [`FooBar`]...
    model_ref_re = re.compile(r"\[`(?P<model>[A-Za-z_][A-Za-z0-9_]*)`\]")

    for idx, line in enumerate(lines, 1):
        match = model_ref_re.search(line)
        if not match:
            continue
        model = match.group("model")
        fields = schema_fields.get(model)
        if fields is None:
            continue

        # Only validate "field-level" claims; skip behavioral sentences where
        # the model name appears but code spans refer to other identifiers.
        if "필수 필드" not in line and "선택적으로" not in line and "required field" not in line.lower():
            continue

        required_tokens = _extract_required_doc_fields(line)
        optional_tokens = _extract_optional_doc_fields(line)
        mentioned_tokens = list(dict.fromkeys(required_tokens + optional_tokens))

        def _field_exists(token: str) -> bool:
            if not token:
                return True
            if token == model:
                return True
            if "*" in token:
                prefix = token.split("*", 1)[0]
                return any(name.startswith(prefix) for name in fields)
            return token in fields

        for token in mentioned_tokens:
            if not _field_exists(token):
                findings.append(
                    Finding(
                        kind="schema_field_missing",
                        doc=str(doc_path.relative_to(ROOT)),
                        line=idx,
                        token=f"{model}.{token}",
                        context=line.strip(),
                    )
                )

        for token in required_tokens:
            if "*" in token:
                prefix = token.split("*", 1)[0]
                candidates = [name for name in fields if name.startswith(prefix)]
                # If the doc claims required but it is a wildcard, treat it as a doc smell.
                for name in candidates:
                    if not fields[name].required:
                        findings.append(
                            Finding(
                                kind="schema_required_mismatch",
                                doc=str(doc_path.relative_to(ROOT)),
                                line=idx,
                                token=f"{model}.{name}",
                                context=f"doc says required but schema is optional: {line.strip()}",
                            )
                        )
                continue
            if token in fields and not fields[token].required:
                findings.append(
                    Finding(
                        kind="schema_required_mismatch",
                        doc=str(doc_path.relative_to(ROOT)),
                        line=idx,
                        token=f"{model}.{token}",
                        context=f"doc says required but schema is optional: {line.strip()}",
                    )
                )

        for token in optional_tokens:
            if "*" in token:
                prefix = token.split("*", 1)[0]
                candidates = [name for name in fields if name.startswith(prefix)]
                for name in candidates:
                    if fields[name].required:
                        findings.append(
                            Finding(
                                kind="schema_required_mismatch",
                                doc=str(doc_path.relative_to(ROOT)),
                                line=idx,
                                token=f"{model}.{name}",
                                context=f"doc says optional but schema is required: {line.strip()}",
                            )
                        )
                continue
            if token in fields and fields[token].required:
                findings.append(
                    Finding(
                        kind="schema_required_mismatch",
                        doc=str(doc_path.relative_to(ROOT)),
                        line=idx,
                        token=f"{model}.{token}",
                        context=f"doc says optional but schema is required: {line.strip()}",
                    )
                )
    return findings


def _iter_status_table(
    lines: list[str], start_idx: int
) -> tuple[set[int], int]:
    """Parse a markdown table of HTTP statuses starting at start_idx (0-based)."""
    statuses: set[int] = set()
    idx = start_idx
    while idx < len(lines):
        line = lines[idx].rstrip("\n")
        if not line.strip().startswith("|"):
            break
        # Skip separator row (---)
        if re.match(r"^\s*\|\s*-+\s*\|", line):
            idx += 1
            continue
        # Extract first 3-digit number in the row.
        match = _HTTP_STATUS_RE.search(line)
        if match:
            statuses.add(int(match.group(1)))
        idx += 1
    return statuses, idx


def _status_table_findings(
    docs_dir: Path,
    *,
    routes: Mapping[tuple[str, str], RouteInfo],
) -> list[Finding]:
    findings: list[Finding] = []
    for md in _iter_md_files(docs_dir):
        lines = _safe_read_text(md).splitlines()
        last_endpoint: tuple[str, str] | None = None
        last_endpoint_line: int | None = None
        for idx, line in enumerate(lines, 1):
            ep = _ENDPOINT_LINE_RE.match(line.strip())
            if ep:
                raw_path = ep.group(2)
                path = raw_path.split("?", 1)[0]
                last_endpoint = (ep.group(1).upper(), path)
                last_endpoint_line = idx
                continue
            if not _looks_like_http_status_table_header(line):
                continue
            if last_endpoint is None or last_endpoint_line is None:
                continue
            if idx - last_endpoint_line > 20:
                continue
            status_set, _ = _iter_status_table(lines, idx)
            route = routes.get(last_endpoint)
            if route is None:
                continue
            expected = route.success_status
            if expected not in status_set:
                findings.append(
                    Finding(
                        kind="status_table_mismatch",
                        doc=str(md.relative_to(ROOT)),
                        line=idx,
                        token=f"{last_endpoint[0]} {last_endpoint[1]}",
                        context=f"expected success {expected} but table had {sorted(status_set)}",
                    )
                )
    return findings


def _doc_status_mismatch_findings(
    doc_path: Path,
    *,
    code_statuses_by_endpoint: Mapping[tuple[str, str], set[int]],
) -> list[Finding]:
    """Check status codes mentioned in endpoint sections are possible per code scan.

    This is intentionally conservative and only enabled for a small set of docs
    where we can build a reasonably accurate status set.
    """
    findings: list[Finding] = []
    lines = _safe_read_text(doc_path).splitlines()

    current_endpoint: tuple[str, str] | None = None
    current_start_line = 0
    section_statuses: set[int] = set()

    def _flush() -> None:
        nonlocal section_statuses, current_endpoint
        if current_endpoint is None:
            section_statuses = set()
            return
        expected = code_statuses_by_endpoint.get(current_endpoint)
        if not expected:
            section_statuses = set()
            return
        for status_code in sorted(section_statuses):
            if status_code not in expected:
                findings.append(
                    Finding(
                        kind="doc_status_not_in_code",
                        doc=str(doc_path.relative_to(ROOT)),
                        line=current_start_line,
                        token=f"{current_endpoint[0]} {current_endpoint[1]} -> {status_code}",
                        context=f"doc mentions {status_code} but code scan suggests {sorted(expected)}",
                    )
                )
        section_statuses = set()

    heading_re = re.compile(r"^###\s+.*`(?P<method>[A-Z]+)\s+(?P<path>/[^`]+)`")
    for idx, line in enumerate(lines, 1):
        heading = heading_re.match(line)
        if heading:
            _flush()
            current_endpoint = (heading.group("method").upper(), heading.group("path"))
            current_start_line = idx
            continue
        if current_endpoint is None:
            continue
        for raw in _HTTP_STATUS_RE.findall(line):
            section_statuses.add(int(raw))

    _flush()
    return findings


def _code_statuses_for_worldservice_endpoints(root: Path) -> dict[tuple[str, str], set[int]]:
    """Build a best-effort status set for WorldService (+ RiskHub) endpoints."""
    endpoints: dict[tuple[str, str], set[int]] = {}

    service_file = root / "qmtl" / "services" / "worldservice" / "services.py"
    service_text = _safe_read_text(service_file)
    service_tree = ast.parse(service_text)
    service_statuses_all = _extract_http_exception_statuses(service_tree)
    service_methods: dict[str, ast.AST] = {}
    for node in ast.walk(service_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            service_methods[node.name] = node

    for py in sorted((root / "qmtl" / "services" / "worldservice" / "routers").glob("*.py")):
        text = _safe_read_text(py)
        tree = ast.parse(text)

        file_statuses = _extract_http_exception_statuses(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                verb = dec.func.attr.lower()
                if verb not in {"get", "post", "put", "delete", "patch"}:
                    continue
                if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
                    continue
                path = str(dec.args[0].value)
                method = verb.upper()
                success = 200
                for kw in dec.keywords:
                    if kw.arg == "status_code":
                        resolved = _to_int_status(kw.value)
                        if resolved is not None:
                            success = resolved
                        break

                statuses = {success}
                statuses.update(file_statuses)

                # Follow `await service.<method>(...)` in the handler body for additional HTTPExceptions.
                called_service_methods: set[str] = set()
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Await) and isinstance(inner.value, ast.Call):
                        call = inner.value
                        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                            if call.func.value.id == "service":
                                called_service_methods.add(call.func.attr)
                for name in called_service_methods:
                    method_node = service_methods.get(name)
                    if method_node is None:
                        continue
                    statuses.update(_extract_http_exception_statuses(method_node))
                if called_service_methods:
                    # Conservative: include service-level status codes from helpers that may be
                    # invoked indirectly (e.g., allocation execution helper raising 503/502).
                    statuses.update(service_statuses_all)

                # FastAPI validation errors are commonly 422; treat as always possible for these APIs.
                statuses.add(422)
                endpoints[(method, path)] = statuses
    return endpoints


def audit_architecture_contracts(docs_dir: Path, *, out: Path) -> list[Finding]:
    routes = _collect_fastapi_routes(ROOT)
    code_error_codes = _collect_error_codes_in_code(ROOT)

    schema_fields = _parse_worldservice_schema_fields(
        ROOT / "qmtl" / "services" / "worldservice" / "schemas.py"
    )

    findings: list[Finding] = []
    findings.extend(_collect_error_code_findings(docs_dir, code_codes=code_error_codes))

    world_doc = docs_dir / "worldservice.md"
    if world_doc.exists():
        findings.extend(_schema_field_findings_for_worldservice_doc(world_doc, schema_fields))

    findings.extend(_status_table_findings(docs_dir, routes=routes))

    # Conservative per-endpoint status scan for docs that assert error semantics.
    ws_statuses = _code_statuses_for_worldservice_endpoints(ROOT)
    for doc_name in ("worldservice.md", "risk_signal_hub.md"):
        doc_path = docs_dir / doc_name
        if doc_path.exists():
            findings.extend(
                _doc_status_mismatch_findings(doc_path, code_statuses_by_endpoint=ws_statuses)
            )

    # Emit report
    findings_sorted = sorted(findings, key=lambda f: (f.kind, f.doc, f.line, f.token))
    counts: dict[str, int] = {}
    for f in findings_sorted:
        counts[f.kind] = counts.get(f.kind, 0) + 1

    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Architecture contract audit (ko)",
        "",
        f"- docs_dir: `{docs_dir}`",
        f"- findings_total: {len(findings_sorted)}",
    ]
    for kind in sorted(counts):
        lines.append(f"- {kind}: {counts[kind]}")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not findings_sorted:
        lines.append("- (none)")
    else:
        for f in findings_sorted:
            lines.append(f"- **{f.kind}** {f.doc}:{f.line} — `{f.token}`")
            lines.append(f"  - {f.context}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return findings_sorted


def main() -> int:
    parser = argparse.ArgumentParser(prog="audit_architecture_contracts")
    parser.add_argument(
        "--docs-dir",
        default=str(ROOT / "docs" / "ko" / "architecture"),
        help="Path to canonical architecture docs (default: docs/ko/architecture)",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "outputs" / "architecture_contract_audit_ko.md"),
        help="Output markdown report path (default: outputs/architecture_contract_audit_ko.md)",
    )
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    out = Path(args.out)
    audit_architecture_contracts(docs_dir=docs_dir, out=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
