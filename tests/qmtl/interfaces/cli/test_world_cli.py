from __future__ import annotations

import json
from pathlib import Path

from qmtl.interfaces.cli import world


def test_allocations_command_lists_snapshots(monkeypatch, capsys):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return 200, {
            "allocations": {
                "w1": {"allocation": 0.6, "strategy_alloc_total": {"s1": 0.4}},
                "w2": {"allocation": 0.4},
            }
        }

    monkeypatch.setattr(world, "http_get", fake_get)

    exit_code = world.cmd_world(["allocations", "--world-id", "demo-world"])

    assert exit_code == 0
    assert calls == [("/allocations", {"world_id": "demo-world"})]
    out = capsys.readouterr().out
    assert "w1: 0.6000" in out
    assert "s1" in out
    assert "qmtl world apply demo-world" in out


def test_rebalance_plan_builds_payload(monkeypatch, tmp_path: Path, capsys):
    positions_file = tmp_path / "positions.json"
    positions_file.write_text(
        json.dumps(
            [
                {
                    "world_id": "w1",
                    "strategy_id": "s1",
                    "symbol": "BTC",
                    "qty": 1,
                    "mark": 20000.0,
                }
            ]
        )
    )

    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"per_world": {"w1": {"scale_world": 1.0, "deltas": []}}, "global_deltas": []}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "rebalance-plan",
            "--target",
            "w1=1.0",
            "--current",
            "w1=0.5",
            "--positions-file",
            str(positions_file),
            "--total-equity",
            "1000",
            "--schema-version",
            "2",
        ]
    )

    assert exit_code == 0
    assert posts[0][0] == "/rebalancing/plan"
    payload = posts[0][1]
    assert payload["world_alloc_after"] == {"w1": 1.0}
    assert payload["world_alloc_before"] == {"w1": 0.5}
    assert payload["positions"][0]["strategy_id"] == "s1"
    assert payload["schema_version"] == 2
    out = capsys.readouterr().out
    assert "Rebalance plan" in out


def test_rebalance_plan_requires_mark(monkeypatch, tmp_path: Path, capsys):
    positions_file = tmp_path / "positions.json"
    positions_file.write_text(
        json.dumps(
            [
                {
                    "world_id": "w1",
                    "strategy_id": "s1",
                    "symbol": "BTC",
                    "qty": 1,
                }
            ]
        )
    )

    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "rebalance-plan",
            "--target",
            "w1=1.0",
            "--current",
            "w1=0.5",
            "--positions-file",
            str(positions_file),
        ]
    )

    assert exit_code == 1
    assert posts == []
    err = capsys.readouterr().err
    assert "mark" in err


def test_rebalance_apply_fetches_current(monkeypatch, capsys):
    gets: list[tuple[str, dict | None]] = []
    posts: list[tuple[str, dict]] = []

    def fake_get(path, params=None):
        gets.append((path, params))
        return 200, {"allocations": {"w1": {"allocation": 0.25}}}

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"per_world": {}, "global_deltas": []}

    monkeypatch.setattr(world, "http_get", fake_get)
    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(["rebalance-apply", "--target", "w1=0.75", "--world-id", "w1"])

    assert exit_code == 0
    assert gets == [("/allocations", {"world_id": "w1"})]
    payload = posts[0][1]
    assert payload["world_alloc_before"] == {"w1": 0.25}
    assert payload["world_alloc_after"] == {"w1": 0.75}
    out = capsys.readouterr().out
    assert "Rebalance plan" in out


def test_rebalance_apply_fails_when_current_snapshot_unavailable(monkeypatch, capsys):
    def fake_get(path, params=None):
        return 502, {"detail": "gateway unavailable"}

    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"per_world": {}, "global_deltas": []}

    monkeypatch.setattr(world, "http_get", fake_get)
    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(["rebalance-apply", "--target", "w1=0.75", "--world-id", "w1"])

    assert exit_code == 1
    assert posts == []
    err = capsys.readouterr().err
    assert "Error fetching allocations" in err


def test_rebalance_apply_requires_snapshot(monkeypatch, capsys):
    def fake_get(path, params=None):
        return 200, {"allocations": {}}

    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"per_world": {}, "global_deltas": []}

    monkeypatch.setattr(world, "http_get", fake_get)
    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(["rebalance-apply", "--target", "w1=0.75", "--world-id", "w1"])

    assert exit_code == 1
    assert posts == []
    err = capsys.readouterr().err
    assert "no allocation snapshot" in err


def test_allocations_warns_on_stale_snapshot(monkeypatch, capsys):
    def fake_get(path, params=None):
        return 200, {"allocations": {"w1": {"allocation": 0.5, "stale": True}}}

    monkeypatch.setattr(world, "http_get", fake_get)

    exit_code = world.cmd_world(["allocations", "--world-id", "w1"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "stale" in out.lower()


def test_allocations_hint_when_snapshot_missing(monkeypatch, capsys):
    def fake_get(path, params=None):
        return 200, {"allocations": {}}

    monkeypatch.setattr(world, "http_get", fake_get)

    exit_code = world.cmd_world(["allocations", "--world-id", "w1"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "No allocation records found" in out
    assert "qmtl world apply w1" in out


def test_world_apply_posts_payload(monkeypatch, capsys):
    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"phase": "completed", "active": ["s1"]}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "apply",
            "w-apply",
            "--plan",
            '{"activate":["s1"],"deactivate":[]}',
            "--run-id",
            "run-123",
        ]
    )

    assert exit_code == 0
    assert posts[0][0] == "/worlds/w-apply/apply"
    payload = posts[0][1]
    assert payload["run_id"] == "run-123"
    assert payload["plan"]["activate"] == ["s1"]
    out = capsys.readouterr().out
    assert "Apply request sent" in out
    assert "run-123" in out


def test_world_apply_builds_plan_from_flags(monkeypatch, capsys):
    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"phase": "completed", "active": ["s1", "s2"]}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "apply",
            "w-apply",
            "--activate",
            "s1,s2",
            "--deactivate",
            "s3",
        ]
    )

    assert exit_code == 0
    payload = posts[0][1]
    assert payload["plan"]["activate"] == ["s1", "s2"]
    assert payload["plan"]["deactivate"] == ["s3"]


def test_world_apply_rejects_conflicting_plan_sources(monkeypatch, capsys):
    def fake_post(path, payload):
        return 200, {}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "apply",
            "w-apply",
            "--plan",
            '{"plan":{"activate":["s1"]}}',
            "--activate",
            "s2",
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "cannot be combined" in err


def test_world_apply_reads_plan_from_wrapped_file(monkeypatch, tmp_path, capsys):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"plan": {"activate": ["s1"]}}))

    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "apply",
            "w-apply",
            "--plan-file",
            str(plan_file),
        ]
    )

    assert exit_code == 0
    assert posts[0][1]["plan"]["activate"] == ["s1"]


def test_world_apply_generates_run_id(monkeypatch, capsys):
    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {}

    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        [
            "apply",
            "w-auto",
        ]
    )

    assert exit_code == 0
    assert posts[0][0] == "/worlds/w-auto/apply"
    generated_run_id = posts[0][1].get("run_id")
    assert generated_run_id
    out = capsys.readouterr().out
    assert "Apply request sent" in out
    assert generated_run_id in out


def test_world_run_status_fetches_run(monkeypatch, capsys):
    gets: list[tuple[str, dict | None]] = []

    def fake_get(path, params=None):
        gets.append((path, params))
        if path == "/worlds/w1/strategies/s1/runs/run-1":
            return 200, {
                "world_id": "w1",
                "strategy_id": "s1",
                "run_id": "run-1",
                "stage": "paper",
                "risk_tier": "low",
                "summary": {"status": "pass", "recommended_stage": "paper_only", "override_status": "approved"},
                "validation": {"policy_version": "1"},
            }
        return 404, {"detail": "not found"}

    monkeypatch.setattr(world, "http_get", fake_get)

    exit_code = world.cmd_world(["run-status", "w1", "--strategy", "s1", "--run", "run-1"])

    assert exit_code == 0
    assert gets == [("/worlds/w1/strategies/s1/runs/run-1", None)]
    out = capsys.readouterr().out
    assert "Evaluation Run" in out
    assert "run-1" in out


def test_world_live_approve_posts_override(monkeypatch, capsys):
    posts: list[tuple[str, dict]] = []

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"summary": {"override_status": payload.get("status")}}

    monkeypatch.setattr(world, "http_post", fake_post)
    monkeypatch.setattr(world, "_utc_now_iso", lambda: "2025-01-02T03:04:05Z")

    exit_code = world.cmd_world(
        [
            "live-approve",
            "w1",
            "--strategy",
            "s1",
            "--run",
            "run-1",
            "--actor",
            "risk",
            "--comment",
            "approved for live",
        ]
    )

    assert exit_code == 0
    assert posts[0][0] == "/worlds/w1/promotions/live/approve"
    assert posts[0][1]["status"] == "approved"
    assert posts[0][1]["strategy_id"] == "s1"
    assert posts[0][1]["run_id"] == "run-1"
    assert posts[0][1]["reason"] == "approved for live"
    assert posts[0][1]["actor"] == "risk"
    assert posts[0][1]["timestamp"] == "2025-01-02T03:04:05Z"
    out = capsys.readouterr().out
    assert "Override recorded" in out


def test_world_live_apply_plan_only(monkeypatch, capsys):
    gets: list[tuple[str, dict | None]] = []
    posts: list[tuple[str, dict]] = []

    def fake_get(path, params=None):
        gets.append((path, params))
        if path == "/worlds/w1/promotions/live/plan":
            return 200, {"plan": {"activate": ["s1"], "deactivate": ["s3"]}}
        return 404, {"detail": "not found"}

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"phase": "completed", "active": ["s1", "s2"]}

    monkeypatch.setattr(world, "http_get", fake_get)
    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(["live-apply", "w1", "--strategy", "s1", "--run", "run-1", "--plan-only"])

    assert exit_code == 0
    assert posts == []
    out = capsys.readouterr().out
    assert '"activate": [' in out
    assert "s1" in out
    assert "s3" in out


def test_world_live_apply_posts_apply(monkeypatch, capsys):
    gets: list[tuple[str, dict | None]] = []
    posts: list[tuple[str, dict]] = []

    def fake_get(path, params=None):
        gets.append((path, params))
        if path == "/worlds/w1/promotions/live/plan":
            return 200, {"plan": {"activate": ["s1"], "deactivate": ["s3"]}}
        return 404, {"detail": "not found"}

    def fake_post(path, payload):
        posts.append((path, payload))
        return 200, {"phase": "completed", "active": ["s1", "s2"]}

    monkeypatch.setattr(world, "http_get", fake_get)
    monkeypatch.setattr(world, "http_post", fake_post)

    exit_code = world.cmd_world(
        ["live-apply", "w1", "--strategy", "s1", "--run", "run-1", "--run-id", "apply-1"]
    )

    assert exit_code == 0
    assert posts[0][0] == "/worlds/w1/promotions/live/apply"
    assert posts[0][1]["apply_run_id"] == "apply-1"
    assert posts[0][1]["strategy_id"] == "s1"
    assert posts[0][1]["run_id"] == "run-1"
    out = capsys.readouterr().out
    assert "Apply request sent" in out
