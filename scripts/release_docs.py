#!/usr/bin/env python3
"""Utilities for synchronizing changelog and archiving documentation."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping
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


def _archive_sources(docs_dir: Path) -> list[Path]:
    locales = ("ko", "en")
    return [docs_dir / locale for locale in locales]


def _render_archive_readme(
    version: str,
    support: str,
    readme_path: Path,
) -> str:
    if readme_path.exists():
        lines = readme_path.read_text().splitlines()
    else:
        lines = ["# Archived Documentation", "", "| Version | Status |", "|--------|--------|"]
    entry = f"| [v{version}](./{version}/) | {support} |"
    if entry not in lines:
        lines.append(entry)
    return "\n".join(lines) + "\n"


def _ensure_archive_paths_exist(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing docs locales: " + ", ".join(missing))


def _transfer_path(src: Path, dst: Path, mode: str) -> None:
    if dst.exists():
        raise FileExistsError(f"Archive destination already exists: {dst}")
    if mode == "copy":
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return
    if mode == "move":
        shutil.move(str(src), dst)
        return
    raise ValueError(f"Unsupported archive mode: {mode}")


def archive_docs(
    version: str,
    support: str = "supported",
    docs_dir: Path = DOCS_DIR,
    archive_dir: Path = ARCHIVE_DIR,
    readme_path: Path = ARCHIVE_README,
    *,
    mode: str = "copy",
    dry_run: bool = False,
) -> None:
    """Archive current docs into a versioned folder and update README."""
    src_items = _archive_sources(docs_dir)
    _ensure_archive_paths_exist(src_items)

    dst_root = archive_dir / version
    actions = []
    for src in src_items:
        dst = dst_root / src.name
        actions.append((src, dst))

    readme_text = _render_archive_readme(version, support, readme_path)

    if dry_run:
        print("[dry-run] archive-docs")
        for src, dst in actions:
            print(f"[dry-run] {mode}: {src} -> {dst}")
        print(f"[dry-run] update README: {readme_path}")
        return

    dst_root.mkdir(parents=True, exist_ok=True)
    for src, dst in actions:
        _transfer_path(src, dst, mode)

    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme_text)


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
    arch.add_argument(
        "--mode",
        choices=("copy", "move"),
        default="copy",
        help="Archive by copying (default) or moving docs",
    )
    arch.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned archive actions without modifying files",
    )

    args = parser.parse_args()
    if args.cmd == "sync-changelog":
        sync_changelog()
    elif args.cmd == "archive-docs":
        archive_docs(args.version, args.status, mode=args.mode, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
