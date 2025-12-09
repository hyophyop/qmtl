from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

DEFAULT_OUTPUT_PATH = "validation_report.md"
MAX_METRIC_ROWS = 20


@dataclass
class RuleResultSummary:
    name: str
    status: str
    severity: str
    owner: str | None
    reason_code: str | None
    reason: str | None
    tags: list[str]


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = yaml.safe_load(raw)
    if not isinstance(data, Mapping):
        raise ValueError(f"expected mapping payload in {path}")
    return dict(data)


def _coerce_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if str(item).strip()]
    return []


def _extract_rule_results(validation: Mapping[str, Any] | None) -> list[RuleResultSummary]:
    if not isinstance(validation, Mapping):
        return []
    container = validation.get("results")
    if not isinstance(container, Mapping):
        return []
    results: list[RuleResultSummary] = []
    for name, payload in container.items():
        if not isinstance(payload, Mapping):
            continue
        results.append(
            RuleResultSummary(
                name=str(name),
                status=_coerce_str(payload.get("status"), "unknown"),
                severity=_coerce_str(payload.get("severity"), ""),
                owner=_coerce_str(payload.get("owner")) or None,
                reason_code=_coerce_str(payload.get("reason_code")) or None,
                reason=_coerce_str(payload.get("reason")) or None,
                tags=_string_list(payload.get("tags")),
            )
        )
    status_order = {"fail": 0, "warn": 1, "pass": 2}
    return sorted(
        results,
        key=lambda r: (status_order.get(r.status, 3), r.severity or "zzz", r.name),
    )


def _flatten_metrics(metrics: Mapping[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    def visit(prefix: list[str], obj: Any) -> None:
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                visit(prefix + [str(key)], value)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            rows.append((".".join(prefix), f"{obj:g}"))
        elif isinstance(obj, str):
            rows.append((".".join(prefix), obj))

    visit([], metrics)
    return rows[:MAX_METRIC_ROWS]


def _render_rule_results(results: list[RuleResultSummary]) -> str:
    if not results:
        return "_No validation results available._"
    lines = ["| Rule | Status | Severity | Owner | Reason |", "| --- | --- | --- | --- | --- |"]
    for item in results:
        reason = item.reason or item.reason_code or ""
        owner = item.owner or ""
        lines.append(
            f"| {item.name} | {item.status.upper()} | {item.severity or ''} | {owner} | {reason} |"
        )
    return "\n".join(lines)


def _render_metric_rows(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No metrics captured in this evaluation run._"
    lines = ["| Metric | Value |", "| --- | --- |"]
    for name, value in rows:
        lines.append(f"| {name} | {value} |")
    return "\n".join(lines)


def _model_card_value(card: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        if key in card:
            return _coerce_str(card.get(key), "")
    return ""


def _summary_line(label: str, value: str | None) -> str:
    return f"- {label}: {value or 'n/a'}"


def generate_markdown_report(evaluation_run: Mapping[str, Any], model_card: Mapping[str, Any]) -> str:
    world_id = _coerce_str(evaluation_run.get("world_id"), "unknown")
    strategy_id = _coerce_str(evaluation_run.get("strategy_id"), "unknown")
    run_id = _coerce_str(evaluation_run.get("run_id"), "unknown")
    stage = _coerce_str(evaluation_run.get("stage"), "unknown")
    risk_tier = _coerce_str(evaluation_run.get("risk_tier"), "unknown")
    summary_raw = evaluation_run.get("summary") if isinstance(evaluation_run, Mapping) else {}
    summary = summary_raw if isinstance(summary_raw, Mapping) else {}
    summary_status = _coerce_str(summary.get("status"), "unknown")
    recommended_stage = _coerce_str(summary.get("recommended_stage"), "")
    model_card_version = _coerce_str(
        evaluation_run.get("model_card_version") or model_card.get("model_card_version"),
        "",
    )
    created_at = _coerce_str(evaluation_run.get("created_at") if isinstance(evaluation_run, Mapping) else "", "")
    updated_at = _coerce_str(evaluation_run.get("updated_at") if isinstance(evaluation_run, Mapping) else "", "")
    validation_raw = evaluation_run.get("validation") if isinstance(evaluation_run, Mapping) else {}
    validation = validation_raw if isinstance(validation_raw, Mapping) else {}
    policy_version = _coerce_str(validation.get("policy_version"), "")
    ruleset_hash = _coerce_str(validation.get("ruleset_hash"), "")
    profile = _coerce_str(validation.get("profile"), "")

    rule_results = _extract_rule_results(validation if isinstance(validation, Mapping) else {})

    metrics_section = evaluation_run.get("metrics") if isinstance(evaluation_run, Mapping) else {}
    metric_rows = _flatten_metrics(metrics_section if isinstance(metrics_section, Mapping) else {})

    objective = _model_card_value(model_card, "objective", "description", "summary")
    scope = _model_card_value(model_card, "scope", "mission")
    universe = _model_card_value(model_card, "universe", "asset_universe")
    data_sources = _string_list(model_card.get("data_sources") or model_card.get("data"))
    features = _string_list(model_card.get("features") or model_card.get("signals"))
    assumptions = _string_list(model_card.get("assumptions"))
    limitations = _string_list(model_card.get("limitations") or model_card.get("risks"))

    lines: list[str] = []
    lines.append(f"# Validation Report — {strategy_id} @ {world_id}")
    lines.append("")
    lines.append("## 0. Summary")
    lines.append(_summary_line("Status", summary_status.upper()))
    lines.append(_summary_line("Recommended stage", recommended_stage or "(not provided)"))
    lines.append(_summary_line("World", world_id))
    lines.append(_summary_line("Strategy", strategy_id))
    lines.append(_summary_line("Run ID", run_id))
    lines.append(_summary_line("Stage", stage))
    lines.append(_summary_line("Risk tier", risk_tier))
    lines.append(_summary_line("Model card version", model_card_version or "(not provided)"))
    lines.append(_summary_line("Validation profile", profile or "(not provided)"))
    lines.append(_summary_line("Policy version", policy_version or "(not provided)"))
    lines.append(_summary_line("Ruleset hash", ruleset_hash or "(not provided)"))
    lines.append(_summary_line("Evaluation created_at", created_at or "(not provided)"))
    lines.append(_summary_line("Updated_at", updated_at or "(not provided)"))
    lines.append(_summary_line("Report generated_at", _now_iso()))

    lines.append("")
    lines.append("## 1. Scope & Objective")
    scope_lines = [
        scope or "Scope not provided.",
        f"Objective: {objective or 'No objective provided.'}",
    ]
    if universe:
        scope_lines.append(f"Universe: {universe}")
    lines.append("\n".join(scope_lines))

    lines.append("")
    lines.append("## 2. Model summary (Model Card)")
    if features:
        lines.append(f"- Features/Signals: {', '.join(features)}")
    if data_sources:
        lines.append(f"- Data sources: {', '.join(data_sources)}")
    if assumptions:
        lines.append(f"- Assumptions: {', '.join(assumptions)}")
    if limitations:
        lines.append(f"- Limitations: {', '.join(limitations)}")
    if not any([features, data_sources, assumptions, limitations]):
        lines.append("Model card fields not provided.")

    lines.append("")
    lines.append("## 3. Validation profile & methods")
    lines.append(_summary_line("Profile", profile or "(not provided)"))
    lines.append(_summary_line("Policy version", policy_version or "(not provided)"))
    lines.append(_summary_line("Ruleset hash", ruleset_hash or "(not provided)"))

    lines.append("")
    lines.append("## 4. Results (Rule outcomes)")
    lines.append(_render_rule_results(rule_results))

    lines.append("")
    lines.append("## 5. Metrics snapshot")
    lines.append(_render_metric_rows(metric_rows))

    lines.append("")
    lines.append("## 6. Limitations & recommendations")
    recommendation = recommended_stage or "N/A"
    lines.append(f"- Recommended stage: {recommendation}")
    if limitations:
        lines.append(f"- Known limitations: {', '.join(limitations)}")
    else:
        lines.append("- Known limitations: n/a")

    return "\n".join(lines).strip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a minimal validation report from an EvaluationRun payload and a Model Card.",
    )
    parser.add_argument(
        "--evaluation-run",
        required=True,
        help="Path to the EvaluationRun payload (JSON or YAML).",
    )
    parser.add_argument(
        "--model-card",
        required=True,
        help="Path to the Model Card payload (JSON or YAML).",
    )
    parser.add_argument(
        "--output",
        help=f"Destination path for the report (default: {DEFAULT_OUTPUT_PATH}; stdout if omitted).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        evaluation_run = _load_payload(Path(args.evaluation_run))
        model_card = _load_payload(Path(args.model_card))
        report = generate_markdown_report(evaluation_run, model_card)
    except Exception as exc:
        raise SystemExit(f"[qmtl] failed to generate report: {exc}") from exc

    output_path = args.output or DEFAULT_OUTPUT_PATH
    if output_path in {"-", "/dev/stdout"}:
        print(report)
        return

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(report, encoding="utf-8")
    print(f"[qmtl] validation report written to {dest}")


if __name__ == "__main__":
    main()
