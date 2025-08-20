import json
import subprocess
import sys
from pathlib import Path


def test_list_alpha_status_json() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "list_alpha_status.py"
    result = subprocess.run(
        [sys.executable, str(script), "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    assert "implemented" in data
    assert "docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md" in data["implemented"]
