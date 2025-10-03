from qmtl.services.gateway.commit_log_cli import build_parser


def test_cli_parser_has_expected_options():
    p = build_parser()
    ns = p.parse_args([
        "--bootstrap",
        "localhost:9092",
        "--topic",
        "commit-log",
        "--group",
        "g1",
        "--metrics-port",
        "9000",
        "--poll-timeout-ms",
        "250",
    ])
    assert ns.bootstrap == "localhost:9092"
    assert ns.topic == "commit-log"
    assert ns.group == "g1"
    assert ns.metrics_port == 9000
    assert ns.poll_timeout_ms == 250

