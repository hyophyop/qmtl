import json
from pathlib import Path

from qmtl.cli import report
from qmtl.transforms.alpha_performance import alpha_performance_node


def test_report_cli_generates_markdown(tmp_path: Path) -> None:
    results = {"returns": [0.1, -0.05, 0.2]}
    input_path = tmp_path / "results.json"
    input_path.write_text(json.dumps(results))
    output_path = tmp_path / "report.md"

    report.run(["--from", str(input_path), "--out", str(output_path)])

    assert output_path.exists()
    content = output_path.read_text()
    metrics = alpha_performance_node(results["returns"])
    assert f"{metrics['sharpe']:.6f}" in content
    assert f"{metrics['max_drawdown']:.6f}" in content
