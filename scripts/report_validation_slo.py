"""Report World Validation SLOs from stored EvaluationRuns.

This script aggregates validation health + missing/error signals over a recent
time window and emits a JSON + Markdown report suitable for CI/cron evidence.

Usage:
  WORLDS_DB_DSN=sqlite:///... WORLDS_REDIS_DSN=redis://... \\
    uv run python scripts/report_validation_slo.py --output validation_slo.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import redis.asyncio as redis

from qmtl.services.worldservice.metrics import parse_timestamp
from qmtl.services.worldservice.storage import PersistentStorage


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_window(*, since_raw: str | None, months: int, until_raw: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    until = parse_timestamp(until_raw) if until_raw else now
    if until is None:
        until = now
    if since_raw:
        since = parse_timestamp(since_raw)
        if since is None:
            raise SystemExit(f"Invalid --since timestamp: {since_raw}")
    else:
        since = until - timedelta(days=int(months) * 30)
    return since, until


def _run_timestamp(run: Mapping[str, Any]) -> datetime | None:
    return parse_timestamp(str(run.get("updated_at") or run.get("created_at") or ""))


def _world_tier(world: Mapping[str, Any]) -> str:
    profile = world.get("risk_profile") if isinstance(world.get("risk_profile"), Mapping) else {}
    tier = str(profile.get("tier") or world.get("tier") or "").lower().strip()
    return tier or "unknown"


def _world_client_critical(world: Mapping[str, Any]) -> bool:
    profile = world.get("risk_profile") if isinstance(world.get("risk_profile"), Mapping) else {}
    return bool(profile.get("client_critical") or world.get("client_critical"))


def _get_nested(mapping: Mapping[str, Any], *path: str) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return cur


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    xs = sorted(values)
    n = len(xs)
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(n - 1, lo + 1)
    frac = pos - lo
    if hi == lo:
        return xs[lo]
    return xs[lo] * (1 - frac) + xs[hi] * frac


@dataclass
class RatioStat:
    total: int
    missing: int
    violations: int
    values: list[float]

    def to_dict(self, *, pcts: Iterable[float] = (0.5, 0.95, 0.99)) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "total": int(self.total),
            "present": int(self.total - self.missing),
            "missing": int(self.missing),
            "violations": int(self.violations),
            "min": min(self.values) if self.values else None,
            "max": max(self.values) if self.values else None,
            "mean": (sum(self.values) / len(self.values)) if self.values else None,
        }
        percentiles: dict[str, float] = {}
        for pct in pcts:
            value = _quantile(self.values, float(pct))
            if value is not None:
                percentiles[f"p{int(pct * 100)}"] = value
        payload["percentiles"] = percentiles
        return payload


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Validation SLO Report")
    lines.append("")
    lines.append(f"- Generated at: {report.get('generated_at')}")
    window = report.get("window") or {}
    lines.append(f"- Window: {window.get('since')} → {window.get('until')}")
    lines.append("")

    thresholds = report.get("thresholds") or {}
    lines.append("## Thresholds")
    lines.append("")
    lines.append(f"- metric_coverage_ratio p95 >= {thresholds.get('coverage_p95_min')}")
    lines.append(f"- rules_executed_ratio p95 >= {thresholds.get('rules_executed_p95_min')}")
    lines.append(f"- missing_metric run ratio <= {thresholds.get('missing_metric_run_ratio_max')}")
    lines.append(f"- rule_error run ratio <= {thresholds.get('rule_error_run_ratio_max')}")
    lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append("| World | Tier | Critical | Stage | Runs | Coverage p95 | Rules p95 | Missing(run) | Error(run) | Ext delay p95 | Breach |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in report.get("groups", []):
        coverage_p95 = _get_nested(row.get("coverage") or {}, "percentiles", "p95")
        rules_p95 = _get_nested(row.get("rules_executed") or {}, "percentiles", "p95")
        ext_p95 = _get_nested(row.get("extended_delay_seconds") or {}, "percentiles", "p95")
        lines.append(
            "| {world} | {tier} | {critical} | {stage} | {runs} | {cov_p95} | {rules_p95} | {miss} | {err} | {ext} | {breach} |".format(
                world=row.get("world_id"),
                tier=row.get("tier"),
                critical=str(bool(row.get("client_critical"))).lower(),
                stage=row.get("stage"),
                runs=row.get("runs_total", 0),
                cov_p95=f"{float(coverage_p95):.3f}" if isinstance(coverage_p95, (int, float)) else "N/A",
                rules_p95=f"{float(rules_p95):.3f}" if isinstance(rules_p95, (int, float)) else "N/A",
                miss=f"{float(row.get('missing_metric_run_ratio') or 0.0):.2%}",
                err=f"{float(row.get('rule_error_run_ratio') or 0.0):.2%}",
                ext=f"{float(ext_p95):.1f}s" if isinstance(ext_p95, (int, float)) else "N/A",
                breach=str(bool(row.get("breached"))).lower(),
            )
        )
    lines.append("")

    breached = [g for g in report.get("groups", []) if g.get("breached") is True]
    if breached:
        lines.append("## Breaches")
        lines.append("")
        for row in breached:
            lines.append(f"- {row.get('world_id')}:{row.get('stage')} → {', '.join(row.get('breach_reasons') or [])}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


async def _build_storage() -> tuple[PersistentStorage, Any]:
    dsn = os.environ.get("WORLDS_DB_DSN")
    redis_dsn = os.environ.get("WORLDS_REDIS_DSN")
    if not dsn or not redis_dsn:
        raise SystemExit("Missing WORLDS_DB_DSN/WORLDS_REDIS_DSN")
    redis_client = redis.from_url(redis_dsn, decode_responses=True)
    storage = await PersistentStorage.create(db_dsn=dsn, redis_client=redis_client)
    return storage, redis_client


async def main() -> None:
    parser = argparse.ArgumentParser(description="Report validation SLOs from EvaluationRun store")
    parser.add_argument("--world", action="append", help="world id(s); default=all")
    parser.add_argument("--stage", action="append", help="stage filter(s); default=all stages")
    parser.add_argument("--months", type=int, default=7, help="Lookback window in months (approx; default=7)")
    parser.add_argument("--since", help="Override window start timestamp (ISO8601)")
    parser.add_argument("--until", help="Override window end timestamp (ISO8601; default=now)")
    parser.add_argument("--min-coverage", type=float, default=0.98, help="Per-run metric_coverage_ratio SLO floor (default=0.98)")
    parser.add_argument("--min-rules-executed", type=float, default=1.0, help="Per-run rules_executed_ratio SLO floor (default=1.0)")
    parser.add_argument("--coverage-p95-min", type=float, default=0.98, help="p95(metric_coverage_ratio) gate (default=0.98)")
    parser.add_argument("--rules-executed-p95-min", type=float, default=1.0, help="p95(rules_executed_ratio) gate (default=1.0)")
    parser.add_argument("--missing-metric-run-ratio-max", type=float, default=0.01, help="Run ratio with missing_metric (default=1%)")
    parser.add_argument("--rule-error-run-ratio-max", type=float, default=0.01, help="Run ratio with rule_error (default=1%)")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--output", help="output path; default=stdout")
    parser.add_argument("--fail", action="store_true", help="exit non-zero if any group breaches thresholds")
    args = parser.parse_args()

    since, until = _parse_window(since_raw=args.since, months=int(args.months), until_raw=args.until)
    if since > until:
        raise SystemExit("--since must be <= --until")

    stage_filter = {str(s).lower() for s in (args.stage or []) if str(s).strip()}

    storage, redis_client = await _build_storage()
    try:
        worlds = args.world
        if not worlds:
            worlds = [w["id"] for w in await storage.list_worlds() if w.get("id")]

        groups: list[dict[str, Any]] = []
        for wid in worlds:
            world = await storage.get_world(wid) or {"id": wid}
            tier = _world_tier(world)
            critical = _world_client_critical(world)
            runs = await storage.list_evaluation_runs(world_id=wid)

            by_stage: dict[str, list[dict[str, Any]]] = {}
            for run in runs:
                stage = str(run.get("stage") or "").lower()
                if stage_filter and stage not in stage_filter:
                    continue
                ts = _run_timestamp(run)
                if ts is None or ts < since or ts > until:
                    continue
                by_stage.setdefault(stage or "unknown", []).append(run)

            for stage, stage_runs in sorted(by_stage.items()):
                total = len(stage_runs)
                if total == 0:
                    continue

                coverage_values: list[float] = []
                coverage_missing = 0
                coverage_violations = 0

                rules_values: list[float] = []
                rules_missing = 0
                rules_violations = 0

                missing_metric_runs = 0
                rule_error_runs = 0
                missing_metric_rule_results = 0
                rule_error_rule_results = 0
                total_rule_results = 0

                extended_delay_values: list[float] = []

                for run in stage_runs:
                    metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
                    cov = _as_float(_get_nested(metrics, "diagnostics", "validation_health", "metric_coverage_ratio"))
                    if cov is None:
                        coverage_missing += 1
                    else:
                        coverage_values.append(cov)
                        if cov < float(args.min_coverage):
                            coverage_violations += 1

                    rex = _as_float(_get_nested(metrics, "diagnostics", "validation_health", "rules_executed_ratio"))
                    if rex is None:
                        rules_missing += 1
                    else:
                        rules_values.append(rex)
                        if rex < float(args.min_rules_executed):
                            rules_violations += 1

                    validation = run.get("validation") if isinstance(run.get("validation"), Mapping) else {}
                    results = validation.get("results") if isinstance(validation.get("results"), Mapping) else {}
                    had_missing_metric = False
                    had_rule_error = False
                    for rr in results.values():
                        if not isinstance(rr, Mapping):
                            continue
                        total_rule_results += 1
                        reason_code = str(rr.get("reason_code") or "").lower()
                        if reason_code == "missing_metric":
                            missing_metric_rule_results += 1
                            had_missing_metric = True
                        elif reason_code == "rule_error":
                            rule_error_rule_results += 1
                            had_rule_error = True
                    if had_missing_metric:
                        missing_metric_runs += 1
                    if had_rule_error:
                        rule_error_runs += 1

                    # Best-effort "extended delay" from created_at -> validation.extended_evaluated_at.
                    created_at = parse_timestamp(str(run.get("created_at") or ""))
                    ext_at = parse_timestamp(str(validation.get("extended_evaluated_at") or ""))
                    if created_at is not None and ext_at is not None:
                        delta = (ext_at - created_at).total_seconds()
                        if delta >= 0:
                            extended_delay_values.append(float(delta))

                coverage = RatioStat(total=total, missing=coverage_missing, violations=coverage_violations, values=coverage_values)
                rules_exec = RatioStat(total=total, missing=rules_missing, violations=rules_violations, values=rules_values)
                ext_delay = RatioStat(total=total, missing=0, violations=0, values=extended_delay_values)

                missing_metric_run_ratio = missing_metric_runs / total if total else 0.0
                rule_error_run_ratio = rule_error_runs / total if total else 0.0

                breach_reasons: list[str] = []
                cov_p95 = _get_nested(coverage.to_dict(), "percentiles", "p95")
                if isinstance(cov_p95, (int, float)) and float(cov_p95) < float(args.coverage_p95_min):
                    breach_reasons.append("coverage_p95")
                rules_p95 = _get_nested(rules_exec.to_dict(), "percentiles", "p95")
                if isinstance(rules_p95, (int, float)) and float(rules_p95) < float(args.rules_executed_p95_min):
                    breach_reasons.append("rules_executed_p95")
                if missing_metric_run_ratio > float(args.missing_metric_run_ratio_max):
                    breach_reasons.append("missing_metric_run_ratio")
                if rule_error_run_ratio > float(args.rule_error_run_ratio_max):
                    breach_reasons.append("rule_error_run_ratio")

                groups.append(
                    {
                        "world_id": wid,
                        "tier": tier,
                        "client_critical": critical,
                        "stage": stage,
                        "runs_total": total,
                        "coverage": coverage.to_dict(),
                        "rules_executed": rules_exec.to_dict(),
                        "missing_metric_run_ratio": missing_metric_run_ratio,
                        "rule_error_run_ratio": rule_error_run_ratio,
                        "missing_metric_rule_results": missing_metric_rule_results,
                        "rule_error_rule_results": rule_error_rule_results,
                        "total_rule_results": total_rule_results,
                        "extended_delay_seconds": ext_delay.to_dict(),
                        "breached": bool(breach_reasons),
                        "breach_reasons": breach_reasons,
                    }
                )

        payload = {
            "generated_at": _iso_now(),
            "window": {"since": _iso_utc(since), "until": _iso_utc(until)},
            "thresholds": {
                "coverage_p95_min": args.coverage_p95_min,
                "rules_executed_p95_min": args.rules_executed_p95_min,
                "missing_metric_run_ratio_max": args.missing_metric_run_ratio_max,
                "rule_error_run_ratio_max": args.rule_error_run_ratio_max,
            },
            "groups": groups,
        }

        if args.format == "json":
            output_text = json.dumps(payload, indent=2)
        else:
            output_text = _render_markdown(payload)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
        else:
            print(output_text)

        if args.fail and any(g.get("breached") for g in groups):
            raise SystemExit("Validation SLO thresholds breached; see report for details.")
    finally:
        await storage.close()
        try:
            await redis_client.aclose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
