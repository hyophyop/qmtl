from __future__ import annotations

from pathlib import Path

from scripts.release_docs import archive_docs, sync_changelog


def test_sync_changelog(tmp_path: Path) -> None:
    root = tmp_path / "CHANGELOG.md"
    root.write_text("# Changelog\n\n## 0.1.0\n\n- init\n")
    doc_dir = tmp_path / "docs" / "reference"
    doc_dir.mkdir(parents=True)
    doc = doc_dir / "CHANGELOG.md"

    sync_changelog(root, doc)

    text = doc.read_text()
    assert "Generated from" in text
    assert "# Changelog" in text
    assert "## 0.1.0" in text


def test_archive_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("home")
    (docs / "guide.md").write_text("guide")
    (docs / "archive").mkdir()

    archive_docs("0.1.0", docs_dir=docs, archive_dir=docs / "archive", readme_path=docs / "archive" / "README.md")

    archived = docs / "archive" / "0.1.0"
    assert (archived / "index.md").read_text() == "home"
    assert (archived / "guide.md").read_text() == "guide"
    readme = (docs / "archive" / "README.md").read_text().splitlines()
    assert "| [v0.1.0](./0.1.0/) | supported |" in readme
    assert list(docs.iterdir()) == [docs / "archive"]
