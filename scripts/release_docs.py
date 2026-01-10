#!/usr/bin/env python3
"""Utilities for synchronizing changelog and archiving documentation."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Mapping
import shutil

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
CHANGELOG_ROOT = ROOT / "CHANGELOG.md"
CHANGELOG_DOCS = {
    "en": DOCS_DIR / "en" / "reference" / "CHANGELOG.md",
    "ko": DOCS_DIR / "ko" / "reference" / "CHANGELOG.md",
}
ARCHIVE_DIR = DOCS_DIR / "archive"
ARCHIVE_README = ARCHIVE_DIR / "README.md"

FRONT_MATTER_BY_LOCALE = {
    "en": """---
title: "Changelog"
tags: []
author: "QMTL Team"
last_modified: {today}
---

<!-- Generated from ../CHANGELOG.md; do not edit manually -->

{{ nav_links() }}
""",
    "ko": """---
title: "변경 이력"
tags: []
author: "QMTL Team"
last_modified: {today}
---

<!-- Generated from ../CHANGELOG.md; do not edit manually -->

{{ nav_links() }}
""",
}

NAV_FOOTER = "\n{{ nav_links() }}\n"


def sync_changelog(
    changelog_root: Path = CHANGELOG_ROOT,
    changelog_docs: Mapping[str, Path] | Path = CHANGELOG_DOCS,
) -> None:
    """Copy root changelog into docs with front matter."""
    text = changelog_root.read_text()
    today = date.today().isoformat()
    if isinstance(changelog_docs, Path):
        front_matter = FRONT_MATTER_BY_LOCALE["en"].format(today=today)
        doc_text = front_matter + "\n" + text + NAV_FOOTER
        changelog_docs.write_text(doc_text)
        return
    for locale, changelog_doc in changelog_docs.items():
        front_matter = FRONT_MATTER_BY_LOCALE[locale].format(today=today)
        doc_text = front_matter + "\n" + text + NAV_FOOTER
        changelog_doc.write_text(doc_text)


def archive_docs(
    version: str,
    support: str = "supported",
    docs_dir: Path = DOCS_DIR,
    archive_dir: Path = ARCHIVE_DIR,
    readme_path: Path = ARCHIVE_README,
) -> None:
    """Move current docs into an archive version and update README."""
    dst = archive_dir / version
    dst.mkdir(parents=True, exist_ok=True)

    for item in docs_dir.iterdir():
        if item.name == "archive":
            continue
        shutil.move(str(item), dst / item.name)

    readme_path.parent.mkdir(parents=True, exist_ok=True)
    if readme_path.exists():
        lines = readme_path.read_text().splitlines()
    else:
        lines = ["# Archived Documentation", "", "| Version | Status |", "|--------|--------|"]
    entry = f"| [v{version}](./{version}/) | {support} |"
    if entry not in lines:
        lines.append(entry)
    readme_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "sync-changelog",
        help="Update docs/{ko,en}/reference/CHANGELOG.md",
    )
    arch = sub.add_parser("archive-docs", help="Archive current docs")
    arch.add_argument("--version", required=True, help="Version to archive")
    arch.add_argument("--status", default="supported", help="Support status")

    args = parser.parse_args()
    if args.cmd == "sync-changelog":
        sync_changelog()
    elif args.cmd == "archive-docs":
        archive_docs(args.version, args.status)


if __name__ == "__main__":
    main()
