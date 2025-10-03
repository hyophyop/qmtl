from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable


LINK_RE = re.compile(r"!??\[[^\]]*\]\(([^)]+)\)")


def _iter_markdown_files(docs_dir: Path) -> Iterable[Path]:
    for p in docs_dir.rglob("*.md"): 
        # Skip archived docs if any special handling is needed later
        yield p


def _is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "mailto:", "tel:"))


def _strip_anchor(url: str) -> str:
    return url.split("#", 1)[0]


def _looks_like_macro(url: str) -> bool:
    # Skip mkdocs-macros like {{ code_url('...') }} or jinja-like
    return "{{" in url or "}}" in url


def _validate_link_target(repo_root: Path, docs_dir: Path, md_file: Path, url: str) -> list[str]:
    errors: list[str] = []
    if _is_external(url):
        return errors
    if _looks_like_macro(url):
        return errors

    target = _strip_anchor(url)
    if not target:
        return errors

    # Ignore bare anchors and non-file references
    if target.startswith(("#", "/")):
        return errors

    # Resolve candidates: relative to file, or relative to docs root
    candidates = [md_file.parent / target, docs_dir / target]
    for c in candidates:
        if c.exists():
            return errors

    errors.append(
        f"Broken link: {md_file.relative_to(repo_root)} -> '{url}' (not found relative to file or docs root)"
    )
    return errors


def _validate_tests_paths(md_file: Path, text: str) -> list[str]:
    errors: list[str] = []
    # Enforce new tests tree under tests/qmtl; flag deprecated subtrees
    deprecated = ["tests/runtime/", "tests/sdk/", "tests/services/"]
    for pat in deprecated:
        if pat in text:
            errors.append(
                f"Deprecated tests path in {md_file}: contains '{pat}'. Use 'tests/qmtl/...' instead."
            )
    return errors


def check_docs_links(repo_root: Path, docs_dir: Path) -> list[str]:
    errors: list[str] = []
    for md in _iter_markdown_files(docs_dir):
        text = md.read_text(encoding="utf-8", errors="ignore")

        # Markdown link targets
        for m in LINK_RE.finditer(text):
            url = m.group(1).strip()
            errors.extend(_validate_link_target(repo_root, docs_dir, md, url))

        # Tests path policy
        errors.extend(_validate_tests_paths(md, text))

    return errors


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    docs_dir = repo_root / "docs"
    if not docs_dir.exists():
        print("docs/ directory not found", file=sys.stderr)
        return 2
    errors = check_docs_links(repo_root, docs_dir)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("Docs link/path check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

