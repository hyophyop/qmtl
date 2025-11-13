import json
from pathlib import Path

from qmtl.interfaces.cli import report
from qmtl.runtime.transforms.alpha_performance import alpha_performance_node


def test_report_cli_generates_markdown(tmp_path: Path) -> None:
    results = {"returns": [0.1, -0.05, 0.2]}
    input_path = tmp_path / "results.json"
    input_path.write_text(json.dumps(results))
    output_path = tmp_path / "report.md"

    report.run(["--from", str(input_path), "--out", str(output_path)])

    assert output_path.exists()
    content = output_path.read_text()
    metrics = alpha_performance_node(results["returns"])
    assert f"{metrics['alpha_performance.sharpe']:.6f}" in content
    assert f"{metrics['alpha_performance.max_drawdown']:.6f}" in content


def test_report_cli_handles_missing_returns(tmp_path: Path, capsys) -> None:
    bad = {"not_returns": [0.1]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    try:
        report.run(["--from", str(path)])
    except SystemExit as e:
        assert e.code == 1
    err = capsys.readouterr().err
    assert "must contain a 'returns' key" in err
