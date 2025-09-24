from __future__ import annotations

import json
from pathlib import Path

from scripts.update_dashboard import update_dashboard


def test_update_dashboard(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    sample = docs_dir / "sample.md"
    sample.write_text("# Sample\n")

    dashboard = docs_dir / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "path": "docs/sample.md",
                        "status": "draft",
                        "owner": "alice",
                        "last_updated": None,
                    }
                ],
                "generated": None,
            }
        )
    )

    update_dashboard(root=tmp_path)

    data = json.loads(dashboard.read_text())
    doc = data["documents"][0]
    assert doc["last_updated"] is not None
    assert data["generated"] is not None
