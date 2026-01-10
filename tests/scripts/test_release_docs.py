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
    ko_dir = docs / "ko"
    en_dir = docs / "en"
    ko_dir.mkdir()
    en_dir.mkdir()
    (ko_dir / "index.md").write_text("ko home")
    (ko_dir / "guide.md").write_text("ko guide")
    (en_dir / "index.md").write_text("en home")
    (en_dir / "guide.md").write_text("en guide")
    (docs / "archive").mkdir()

    archive_docs("0.1.0", docs_dir=docs, archive_dir=docs / "archive", readme_path=docs / "archive" / "README.md")

    archived = docs / "archive" / "0.1.0"
    assert (archived / "ko" / "index.md").read_text() == "ko home"
    assert (archived / "ko" / "guide.md").read_text() == "ko guide"
    assert (archived / "en" / "index.md").read_text() == "en home"
    assert (archived / "en" / "guide.md").read_text() == "en guide"
    readme = (docs / "archive" / "README.md").read_text().splitlines()
    assert "| [v0.1.0](./0.1.0/) | supported |" in readme
    assert (docs / "ko" / "index.md").read_text() == "ko home"
    assert (docs / "en" / "index.md").read_text() == "en home"
