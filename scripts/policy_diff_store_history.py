"""Policy diff regression report over stored EvaluationRuns.

This script loads EvaluationRuns from the WorldService Evaluation Store for a recent
time window and computes an old-vs-new policy diff report (JSON + Markdown).

Usage:
  WORLDS_DB_DSN=sqlite:///... WORLDS_REDIS_DSN=redis://... \\
    uv run python scripts/policy_diff_store_history.py \\
      --old docs/ko/world/sample_policy.yml \\
      --new docs/ko/world/sample_policy.yml \\
      --stage backtest \\
      --months 12 \\
      --world w1 \\
      --output policy_diff_history.json \\
      --output-md policy_diff_history.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import redis.asyncio as redis

from qmtl.services.worldservice.metrics import parse_timestamp
from qmtl.services.worldservice.storage import PersistentStorage

try:
    from scripts.policy_diff import PolicyDiffReport, StrategyDiff, _load_policy, compute_policy_diff
except ModuleNotFoundError:  # pragma: no cover
    from policy_diff import PolicyDiffReport, StrategyDiff, _load_policy, compute_policy_diff


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_timestamp(run: Mapping[str, Any]) -> datetime | None:
    return parse_timestamp(str(run.get("updated_at") or run.get("created_at") or ""))


def _status_rank(status: str | None) -> int:
    if status == "pass":
        return 0
    if status == "warn":
        return 1
    if status == "fail":
        return 2
    return -1


def _top_offenders(diffs: list[StrategyDiff], limit: int) -> list[StrategyDiff]:
    candidates = [d for d in diffs if d.has_changes]

    def key(diff: StrategyDiff) -> tuple[int, int, int, int, int]:
        delta = abs(_status_rank(diff.new_status) - _status_rank(diff.old_status))
        return (
            1 if diff.status_changed else 0,
            delta,
            1 if diff.stage_changed else 0,
            1 if diff.selection_changed else 0,
            len(diff.rule_changes or []),
        )

    return sorted(candidates, key=key, reverse=True)[: max(0, int(limit))]


def _render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Policy Diff — EvaluationRun History Report")
    lines.append("")
    lines.append(f"- Generated at: {report.get('generated_at')}")
    window = report.get("window") or {}
    lines.append(f"- Window: {window.get('since')} → {window.get('until')}")
    lines.append(f"- Stage: {report.get('stage')}")
    sampling = report.get("sampling") or {}
    lines.append(
        "- Sampling: dedupe={dedupe}, mode={mode}, max_items={max_items}".format(
            dedupe=sampling.get("dedupe"),
            mode=sampling.get("mode"),
            max_items=sampling.get("max_items"),
        )
    )
    policies = report.get("policies") or {}
    lines.append(f"- Old policy: `{policies.get('old')}`")
    lines.append(f"- New policy: `{policies.get('new')}`")
    threshold = report.get("fail_impact_ratio")
    if threshold is not None:
        lines.append(f"- Fail impact ratio: {threshold}")
    lines.append("")

    worlds = report.get("worlds") or []
    for world_entry in worlds:
        world_id = world_entry.get("world_id") or "<unknown>"
        lines.append(f"## {world_id}")
        lines.append("")
        lines.append(f"- Items evaluated: {world_entry.get('items_evaluated', 0)}")
        lines.append(f"- Items skipped (missing timestamp): {world_entry.get('items_skipped_no_ts', 0)}")
        lines.append(f"- Items in window (pre-sample): {world_entry.get('items_in_window', 0)}")
        diff_report = world_entry.get("policy_diff") or {}
        impact_ratio = float(diff_report.get("impact_ratio") or 0.0)
        lines.append(
            "- Impact: {affected}/{total} ({ratio:.1%})".format(
                affected=diff_report.get("strategies_affected", 0),
                total=diff_report.get("total_strategies", 0),
                ratio=impact_ratio,
            )
        )
        lines.append(
            "- Changes: status={status}, stage={stage}, selection={selection}".format(
                status=diff_report.get("status_changes", 0),
                stage=diff_report.get("stage_changes", 0),
                selection=diff_report.get("selection_changes", 0),
            )
        )
        if world_entry.get("threshold_breached") is True:
            lines.append("- Threshold breached: true")
        lines.append("")

        offenders = world_entry.get("top_offenders") or []
        if offenders:
            lines.append("| Strategy | Run ID | Status | Rule changes |")
            lines.append("| --- | --- | --- | --- |")
            for item in offenders:
                old_status = item.get("old_status") or "N/A"
                new_status = item.get("new_status") or "N/A"
                rule_changes = item.get("rule_changes") or []
                lines.append(
                    "| {sid} | {rid} | {old} → {new} | {n} |".format(
                        sid=item.get("strategy_id") or item.get("id") or "",
                        rid=item.get("run_id") or "",
                        old=old_status,
                        new=new_status,
                        n=len(rule_changes) if isinstance(rule_changes, list) else 0,
                    )
                )
            lines.append("")
        else:
            lines.append("No impacted entries in this window.")
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


def _sample_runs(
    runs: list[dict[str, Any]],
    *,
    mode: str,
    max_items: int | None,
    seed: int,
) -> list[dict[str, Any]]:
    if max_items is None:
        return runs
    cap = max(0, int(max_items))
    if len(runs) <= cap:
        return runs

    def sort_key(run: Mapping[str, Any]) -> tuple[datetime, str, str]:
        ts = _run_timestamp(run) or datetime.min.replace(tzinfo=timezone.utc)
        sid = str(run.get("strategy_id") or "")
        rid = str(run.get("run_id") or "")
        return (ts, sid, rid)

    ordered = sorted(runs, key=sort_key, reverse=True)
    if mode == "latest":
        return ordered[:cap]
    rng = random.Random(int(seed))
    # Sample from a stable ordering for deterministic output.
    idxs = sorted(rng.sample(range(len(ordered)), cap))
    return [ordered[i] for i in idxs]


def _dedupe_latest_by_strategy(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for run in runs:
        sid = str(run.get("strategy_id") or "")
        if not sid:
            continue
        ts = _run_timestamp(run)
        if ts is None:
            continue
        prev = latest.get(sid)
        if prev is None or ts > prev[0]:
            latest[sid] = (ts, run)
    return [entry[1] for entry in latest.values()]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Policy diff report over EvaluationRun history (store-backed)")
    parser.add_argument("--world", action="append", help="world id(s); default=all")
    parser.add_argument("--stage", default="backtest", help="Validation stage filter (backtest/paper/live)")
    parser.add_argument("--months", type=int, default=12, help="Lookback window in months (approx; default=12)")
    parser.add_argument("--since", help="Override window start timestamp (ISO8601)")
    parser.add_argument("--until", help="Override window end timestamp (ISO8601; default=now)")
    parser.add_argument("--dedupe", choices=["strategy", "none"], default="strategy", help="Dedupe policy (default=strategy)")
    parser.add_argument("--sample-mode", choices=["latest", "random"], default="latest")
    parser.add_argument("--max-items", type=int, default=2000, help="Max items per world (post-filter, pre-eval)")
    parser.add_argument("--seed", type=int, default=0, help="Random seed (when sample-mode=random)")
    parser.add_argument("--top", type=int, default=20, help="Top offenders per world (default=20)")
    parser.add_argument("--old", required=True, type=Path, help="Path to old/baseline policy YAML/JSON")
    parser.add_argument("--new", required=True, type=Path, help="Path to new/candidate policy YAML/JSON")
    parser.add_argument("--output", help="Write JSON report to path (default: stdout)")
    parser.add_argument("--output-md", help="Write Markdown report to path (optional)")
    parser.add_argument("--fail-impact-ratio", type=float, default=None, help="Fail if any world impact_ratio >= threshold (0~1)")
    args = parser.parse_args()

    stage = str(args.stage or "").lower()
    since, until = _parse_window(since_raw=args.since, months=int(args.months), until_raw=args.until)
    if since > until:
        raise SystemExit("--since must be <= --until")

    old_policy = _load_policy(args.old)
    new_policy = _load_policy(args.new)

    storage, redis_client = await _build_storage()
    try:
        worlds = args.world
        if not worlds:
            worlds = [w["id"] for w in await storage.list_worlds() if w.get("id")]

        world_reports: list[dict[str, Any]] = []
        breached: list[dict[str, Any]] = []
        total_items_evaluated = 0
        for wid in worlds:
            runs = await storage.list_evaluation_runs(world_id=wid)
            in_window: list[dict[str, Any]] = []
            skipped_no_ts = 0
            for run in runs:
                if stage and str(run.get("stage") or "").lower() != stage:
                    continue
                ts = _run_timestamp(run)
                if ts is None:
                    skipped_no_ts += 1
                    continue
                if ts < since or ts > until:
                    continue
                in_window.append(dict(run))

            deduped = in_window
            if args.dedupe == "strategy":
                deduped = _dedupe_latest_by_strategy(deduped)

            sampled = _sample_runs(
                deduped,
                mode=str(args.sample_mode),
                max_items=int(args.max_items) if args.max_items is not None else None,
                seed=int(args.seed),
            )

            meta: dict[str, dict[str, Any]] = {}
            eval_runs: list[dict[str, Any]] = []
            for run in sampled:
                sid = str(run.get("strategy_id") or "")
                rid = str(run.get("run_id") or "")
                if not sid:
                    continue
                key = sid if args.dedupe == "strategy" else f"{sid}@{rid}"
                meta[key] = {
                    "strategy_id": sid,
                    "run_id": rid,
                    "created_at": run.get("created_at"),
                    "updated_at": run.get("updated_at"),
                }
                run_for_eval = dict(run)
                run_for_eval["strategy_id"] = key
                eval_runs.append(run_for_eval)

            report = compute_policy_diff(
                old_policy,
                new_policy,
                eval_runs,
                stage=stage or None,
                old_version=str(args.old),
                new_version=str(args.new),
            )
            offenders = _top_offenders(report.diffs, limit=int(args.top))
            offenders_payload: list[dict[str, Any]] = []
            for diff in offenders:
                entry = meta.get(diff.strategy_id, {})
                delta = _status_rank(diff.new_status) - _status_rank(diff.old_status)
                offenders_payload.append(
                    {
                        "id": diff.strategy_id,
                        "strategy_id": entry.get("strategy_id") or diff.strategy_id,
                        "run_id": entry.get("run_id"),
                        "created_at": entry.get("created_at"),
                        "updated_at": entry.get("updated_at"),
                        "direction": "tightened" if delta > 0 else "relaxed" if delta < 0 else "other",
                        "old_selected": diff.old_selected,
                        "new_selected": diff.new_selected,
                        "old_recommended_stage": diff.old_recommended_stage,
                        "new_recommended_stage": diff.new_recommended_stage,
                        "old_status": diff.old_status,
                        "new_status": diff.new_status,
                        "rule_changes": list(diff.rule_changes or []),
                    }
                )

            impact_ratio = report.impact_ratio
            threshold_breached = False
            if args.fail_impact_ratio is not None and impact_ratio >= float(args.fail_impact_ratio):
                threshold_breached = True
                breached.append(
                    {
                        "world_id": wid,
                        "impact_ratio": impact_ratio,
                        "affected": report.strategies_affected,
                        "total": report.total_strategies,
                    }
                )

            world_reports.append(
                {
                    "world_id": wid,
                    "items_in_window": len(in_window),
                    "items_skipped_no_ts": skipped_no_ts,
                    "items_evaluated": len(eval_runs),
                    "threshold_breached": threshold_breached,
                    "policy_diff": report.to_dict(),
                    "top_offenders": offenders_payload,
                }
            )
            total_items_evaluated += len(eval_runs)

        payload = {
            "generated_at": _iso_now(),
            "stage": stage,
            "window": {"since": _iso_utc(since), "until": _iso_utc(until)},
            "sampling": {
                "dedupe": args.dedupe,
                "mode": args.sample_mode,
                "max_items": args.max_items,
                "seed": args.seed,
            },
            "policies": {"old": str(args.old), "new": str(args.new)},
            "fail_impact_ratio": args.fail_impact_ratio,
            "summary": {
                "worlds_scanned": len(worlds),
                "items_evaluated_total": total_items_evaluated,
                "threshold_breaches": len(breached),
            },
            "breaches": breached,
            "worlds": world_reports,
        }

        json_text = json.dumps(payload, indent=2)
        md_text = _render_markdown(payload)

        if args.output:
            Path(args.output).write_text(json_text + "\n", encoding="utf-8")
        else:
            print(json_text)

        if args.output_md:
            Path(args.output_md).write_text(md_text, encoding="utf-8")

        if args.fail_impact_ratio is not None and breached:
            max_breach = max(breached, key=lambda b: float(b.get("impact_ratio") or 0.0))
            raise SystemExit(
                "Impact ratio threshold breached: "
                f"{max_breach.get('world_id')} impact_ratio={float(max_breach.get('impact_ratio') or 0.0):.3f} "
                f"(threshold={float(args.fail_impact_ratio):.3f})"
            )
    finally:
        await storage.close()
        try:
            await redis_client.aclose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())

