import json
import subprocess
import sys
from pathlib import Path


def test_select_alpha_includes_priority_and_tags() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "select_alpha.py"
    result = subprocess.run(
        [sys.executable, str(script), "--top", "1"],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    assert data
    entry = data[0]
    assert entry.get("priority")
    assert isinstance(entry.get("tags"), list)
