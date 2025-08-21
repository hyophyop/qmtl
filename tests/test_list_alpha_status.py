import json
import subprocess
import sys
from pathlib import Path

import yaml


def _get_one_implemented_doc() -> str:
    """Return the path of one implemented AlphaDoc from the registry."""
    registry = Path(__file__).resolve().parents[1] / "docs" / "alphadocs_registry.yml"
    entries = yaml.safe_load(registry.read_text())
    for entry in entries or []:
        if entry.get("status") == "implemented":
            return entry["doc"]
    raise AssertionError("No implemented docs found in registry")


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
    implemented_docs = {e["doc"] for e in data["implemented"]}
    target = _get_one_implemented_doc()
    assert target in implemented_docs
    entry = next(e for e in data["implemented"] if e["doc"] == target)
    assert entry.get("priority")
    assert isinstance(entry.get("tags"), list)
