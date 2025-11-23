import pytest

from qmtl.services.gateway import commit_log_cli


def test_build_parser_requires_arguments() -> None:
    parser = commit_log_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_build_parser_assigns_defaults() -> None:
    parser = commit_log_cli.build_parser()
    args = parser.parse_args(
        [
            "--bootstrap",
            "localhost:9092",
            "--topic",
            "topic-a",
            "--group",
            "group-a",
        ]
    )

    assert args.metrics_port == 8000
    assert args.health_port == 0
    assert args.poll_timeout_ms == 500


def test_main_runs_with_metrics_and_health(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    async def fake_run(bootstrap: str, topic: str, group: str, poll_timeout_ms: int) -> None:
        recorded["run"] = (bootstrap, topic, group, poll_timeout_ms)

    started_metrics: list[int] = []
    health_ports: list[int] = []

    monkeypatch.setattr(commit_log_cli, "run", fake_run)
    monkeypatch.setattr(
        commit_log_cli.gw_metrics,
        "start_metrics_server",
        lambda port: started_metrics.append(port),
    )
    monkeypatch.setattr(commit_log_cli, "_start_health_server", health_ports.append)

    exit_code = commit_log_cli.main(
        [
            "--bootstrap",
            "localhost:9092",
            "--topic",
            "topic-a",
            "--group",
            "group-a",
            "--metrics-port",
            "9000",
            "--health-port",
            "9001",
            "--poll-timeout-ms",
            "250",
        ]
    )

    assert exit_code == 0
    assert recorded["run"] == ("localhost:9092", "topic-a", "group-a", 250)
    assert started_metrics == [9000]
    assert health_ports == [9001]


def test_main_skips_health_server_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(*_: object, **__: object) -> None:
        return

    started_metrics: list[int] = []
    health_ports: list[int] = []

    monkeypatch.setattr(commit_log_cli, "run", fake_run)
    monkeypatch.setattr(
        commit_log_cli.gw_metrics,
        "start_metrics_server",
        lambda port: started_metrics.append(port),
    )
    monkeypatch.setattr(commit_log_cli, "_start_health_server", health_ports.append)

    exit_code = commit_log_cli.main(
        [
            "--bootstrap",
            "localhost:9092",
            "--topic",
            "topic-a",
            "--group",
            "group-a",
        ]
    )

    assert exit_code == 0
    assert started_metrics == [8000]
    assert health_ports == []
