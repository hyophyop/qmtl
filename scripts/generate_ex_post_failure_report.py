"""Generate an ex-post failure report from stored EvaluationRuns.

Ex-post failures capture cases where validation *passed*, but a live strategy was
later classified as a failure that should have been avoided. The report aggregates
confirmed ex-post failures by month/quarter, with tier breakdowns.

Usage:
  WORLDS_DB_DSN=sqlite:///... WORLDS_REDIS_DSN=redis://... \\
    uv run python scripts/generate_ex_post_failure_report.py --output ex_post_failures.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

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


def _month_key(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m")


def _quarter_key(ts: datetime) -> str:
    ts_utc = ts.astimezone(timezone.utc)
    q = ((ts_utc.month - 1) // 3) + 1
    return f"{ts_utc.year}-Q{q}"


def _world_tier(world: Mapping[str, Any]) -> str:
    profile = world.get("risk_profile") if isinstance(world.get("risk_profile"), Mapping) else {}
    tier = str(profile.get("tier") or world.get("tier") or "").lower().strip()
    return tier or "unknown"


def _world_client_critical(world: Mapping[str, Any]) -> bool:
    profile = world.get("risk_profile") if isinstance(world.get("risk_profile"), Mapping) else {}
    return bool(profile.get("client_critical") or world.get("client_critical"))


def _run_timestamp(run: Mapping[str, Any]) -> datetime | None:
    return parse_timestamp(str(run.get("updated_at") or run.get("created_at") or ""))


def _summary_status(run: Mapping[str, Any]) -> str | None:
    summary = run.get("summary") if isinstance(run.get("summary"), Mapping) else {}
    status = str(summary.get("status") or "").lower().strip()
    return status or None


def _extract_confirmed_cases(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = run.get("summary") if isinstance(run.get("summary"), Mapping) else {}
    raw = summary.get("ex_post_failures")
    if not isinstance(raw, list):
        return []
    latest_by_case: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            continue
        ts = parse_timestamp(str(item.get("recorded_at") or ""))
        if ts is None:
            continue
        payload = dict(item)
        prev = latest_by_case.get(case_id)
        if prev is None or ts > prev[0]:
            latest_by_case[case_id] = (ts, payload)

    confirmed: list[dict[str, Any]] = []
    for case_id, (ts, payload) in latest_by_case.items():
        status = str(payload.get("status") or "").lower().strip()
        if status != "confirmed":
            continue
        payload = dict(payload)
        payload.setdefault("case_id", case_id)
        payload.setdefault("recorded_at", _iso_utc(ts))
        confirmed.append(payload)
    return confirmed


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Ex-post Failure Report")
    lines.append("")
    lines.append(f"- Generated at: {report.get('generated_at')}")
    window = report.get("window") or {}
    lines.append(f"- Window: {window.get('since')} → {window.get('until')}")
    lines.append(f"- Stage: {report.get('stage')}")
    lines.append("")

    summary = report.get("summary") or {}
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Worlds scanned: {summary.get('worlds_scanned', 0)}")
    lines.append(f"- Pass strategies (window): {summary.get('pass_strategies_total', 0)}")
    lines.append(f"- Ex-post confirmed cases (window): {summary.get('confirmed_cases_total', 0)}")
    lines.append(f"- Ex-post affected strategies (window): {summary.get('affected_strategies_total', 0)}")
    lines.append("")

    lines.append("## Monthly Rates")
    lines.append("")
    lines.append("| Month | Pass strategies | Affected strategies | Confirmed cases | Rate |")
    lines.append("| --- | --- | --- | --- | --- |")
    for month, row in sorted((report.get("monthly") or {}).items()):
        denom = int(row.get("pass_strategies") or 0)
        affected = int(row.get("affected_strategies") or 0)
        cases = int(row.get("confirmed_cases") or 0)
        rate = (affected / denom) if denom else 0.0
        lines.append(f"| {month} | {denom} | {affected} | {cases} | {rate:.2%} |")
    lines.append("")

    lines.append("## Quarterly Rates")
    lines.append("")
    lines.append("| Quarter | Pass strategies | Affected strategies | Confirmed cases | Rate |")
    lines.append("| --- | --- | --- | --- | --- |")
    for quarter, row in sorted((report.get("quarterly") or {}).items()):
        denom = int(row.get("pass_strategies") or 0)
        affected = int(row.get("affected_strategies") or 0)
        cases = int(row.get("confirmed_cases") or 0)
        rate = (affected / denom) if denom else 0.0
        lines.append(f"| {quarter} | {denom} | {affected} | {cases} | {rate:.2%} |")
    lines.append("")

    lines.append("## Tier Breakdown (Window)")
    lines.append("")
    lines.append("| Tier | Client critical | Pass strategies | Affected strategies | Confirmed cases | Rate |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in report.get("tier_breakdown", []):
        denom = int(row.get("pass_strategies") or 0)
        affected = int(row.get("affected_strategies") or 0)
        cases = int(row.get("confirmed_cases") or 0)
        rate = (affected / denom) if denom else 0.0
        lines.append(
            "| {tier} | {cc} | {denom} | {affected} | {cases} | {rate:.2%} |".format(
                tier=row.get("tier"),
                cc=str(bool(row.get("client_critical"))).lower(),
                denom=denom,
                affected=affected,
                cases=cases,
                rate=rate,
            )
        )
    lines.append("")

    lines.append("## Top Categories (Confirmed Cases)")
    lines.append("")
    lines.append("| Category | Cases |")
    lines.append("| --- | --- |")
    for category, count in sorted((report.get("by_category") or {}).items(), key=lambda kv: (-int(kv[1]), kv[0])):
        lines.append(f"| {category} | {int(count)} |")
    lines.append("")

    lines.append("## Top Reason Codes (Confirmed Cases)")
    lines.append("")
    lines.append("| Reason code | Cases |")
    lines.append("| --- | --- |")
    for reason, count in sorted((report.get("by_reason_code") or {}).items(), key=lambda kv: (-int(kv[1]), kv[0])):
        lines.append(f"| {reason} | {int(count)} |")
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
    parser = argparse.ArgumentParser(description="Generate ex-post failure report from EvaluationRun store")
    parser.add_argument("--world", action="append", help="world id(s); default=all")
    parser.add_argument("--stage", default="live", help="EvaluationRun stage filter (default=live)")
    parser.add_argument("--months", type=int, default=12, help="Lookback window in months (approx; default=12)")
    parser.add_argument("--since", help="Override window start timestamp (ISO8601)")
    parser.add_argument("--until", help="Override window end timestamp (ISO8601; default=now)")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--output", help="output path; default=stdout")
    args = parser.parse_args()

    stage = str(args.stage or "").lower()
    since, until = _parse_window(since_raw=args.since, months=int(args.months), until_raw=args.until)
    if since > until:
        raise SystemExit("--since must be <= --until")

    storage, redis_client = await _build_storage()
    try:
        worlds = args.world
        if not worlds:
            worlds = [w["id"] for w in await storage.list_worlds() if w.get("id")]

        monthly_pass: dict[tuple[str, str], set[str]] = {}
        quarterly_pass: dict[tuple[str, str], set[str]] = {}
        monthly_cases: dict[tuple[str, str], set[str]] = {}
        quarterly_cases: dict[tuple[str, str], set[str]] = {}
        monthly_affected: dict[tuple[str, str], set[str]] = {}
        quarterly_affected: dict[tuple[str, str], set[str]] = {}

        tier_agg: dict[tuple[str, bool], dict[str, set[str]]] = {}
        by_category: dict[str, int] = {}
        by_reason: dict[str, int] = {}

        pass_strategies_window: set[str] = set()
        affected_strategies_window: set[str] = set()
        confirmed_cases_window: set[str] = set()

        worlds_scanned = 0
        for wid in worlds:
            world = await storage.get_world(wid) or {"id": wid}
            tier = _world_tier(world)
            client_critical = _world_client_critical(world)
            worlds_scanned += 1

            runs = await storage.list_evaluation_runs(world_id=wid)
            for run in runs:
                if stage and str(run.get("stage") or "").lower() != stage:
                    continue
                ts = _run_timestamp(run)
                if ts is None or ts < since or ts > until:
                    continue
                sid = str(run.get("strategy_id") or "")
                if not sid:
                    continue

                status = _summary_status(run)
                if status == "pass":
                    month = _month_key(ts)
                    quarter = _quarter_key(ts)
                    monthly_pass.setdefault((wid, month), set()).add(f"{wid}:{sid}")
                    quarterly_pass.setdefault((wid, quarter), set()).add(f"{wid}:{sid}")
                    pass_strategies_window.add(f"{wid}:{sid}")
                    tier_key = (tier, client_critical)
                    tier_bucket = tier_agg.setdefault(
                        tier_key,
                        {"pass": set(), "affected": set(), "cases": set()},
                    )
                    tier_bucket["pass"].add(f"{wid}:{sid}")

                confirmed = _extract_confirmed_cases(run)
                if not confirmed:
                    continue
                for case in confirmed:
                    case_id = str(case.get("case_id") or "").strip()
                    recorded_at = parse_timestamp(str(case.get("recorded_at") or ""))
                    if not case_id or recorded_at is None:
                        continue
                    if recorded_at < since or recorded_at > until:
                        continue
                    month = _month_key(recorded_at)
                    quarter = _quarter_key(recorded_at)

                    monthly_cases.setdefault((wid, month), set()).add(case_id)
                    quarterly_cases.setdefault((wid, quarter), set()).add(case_id)
                    monthly_affected.setdefault((wid, month), set()).add(f"{wid}:{sid}")
                    quarterly_affected.setdefault((wid, quarter), set()).add(f"{wid}:{sid}")
                    affected_strategies_window.add(f"{wid}:{sid}")
                    confirmed_cases_window.add(case_id)

                    tier_key = (tier, client_critical)
                    tier_bucket = tier_agg.setdefault(
                        tier_key,
                        {"pass": set(), "affected": set(), "cases": set()},
                    )
                    tier_bucket["affected"].add(f"{wid}:{sid}")
                    tier_bucket["cases"].add(case_id)

                    category = str(case.get("category") or "").strip() or "unknown"
                    reason_code = str(case.get("reason_code") or "").strip() or "unknown"
                    by_category[category] = by_category.get(category, 0) + 1
                    by_reason[reason_code] = by_reason.get(reason_code, 0) + 1

        monthly: dict[str, dict[str, int]] = {}
        quarterly: dict[str, dict[str, int]] = {}

        # Aggregate across worlds per period.
        all_months = sorted({month for (_, month) in monthly_pass.keys()} | {month for (_, month) in monthly_cases.keys()})
        for month in all_months:
            pass_set: set[str] = set()
            affected_set: set[str] = set()
            case_set: set[str] = set()
            for wid in worlds:
                pass_set |= monthly_pass.get((wid, month), set())
                affected_set |= monthly_affected.get((wid, month), set())
                case_set |= monthly_cases.get((wid, month), set())
            monthly[month] = {
                "pass_strategies": len(pass_set),
                "affected_strategies": len(affected_set),
                "confirmed_cases": len(case_set),
            }

        all_quarters = sorted(
            {q for (_, q) in quarterly_pass.keys()} | {q for (_, q) in quarterly_cases.keys()}
        )
        for quarter in all_quarters:
            pass_set = set()
            affected_set = set()
            case_set = set()
            for wid in worlds:
                pass_set |= quarterly_pass.get((wid, quarter), set())
                affected_set |= quarterly_affected.get((wid, quarter), set())
                case_set |= quarterly_cases.get((wid, quarter), set())
            quarterly[quarter] = {
                "pass_strategies": len(pass_set),
                "affected_strategies": len(affected_set),
                "confirmed_cases": len(case_set),
            }

        tier_breakdown: list[dict[str, Any]] = []
        for (tier, client_critical), bucket in sorted(tier_agg.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            tier_breakdown.append(
                {
                    "tier": tier,
                    "client_critical": client_critical,
                    "pass_strategies": len(bucket.get("pass", set())),
                    "affected_strategies": len(bucket.get("affected", set())),
                    "confirmed_cases": len(bucket.get("cases", set())),
                }
            )

        report_payload = {
            "generated_at": _iso_now(),
            "stage": stage,
            "window": {"since": _iso_utc(since), "until": _iso_utc(until)},
            "summary": {
                "worlds_scanned": worlds_scanned,
                "pass_strategies_total": len(pass_strategies_window),
                "affected_strategies_total": len(affected_strategies_window),
                "confirmed_cases_total": len(confirmed_cases_window),
            },
            "monthly": monthly,
            "quarterly": quarterly,
            "tier_breakdown": tier_breakdown,
            "by_category": by_category,
            "by_reason_code": by_reason,
        }

        if args.format == "json":
            output_text = json.dumps(report_payload, indent=2)
        else:
            output_text = _render_markdown(report_payload)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
        else:
            print(output_text)
    finally:
        await storage.close()
        try:
            await redis_client.aclose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
