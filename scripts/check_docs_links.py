from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable
import yaml


LINK_RE = re.compile(r"!??\[[^\]]*\]\(([^)]+)\)")
EN_CORE_ARCH_DOCS = {
    "architecture.md",
    "gateway.md",
    "worldservice.md",
    "controlbus.md",
    "dag-manager.md",
    "ack_resync_rfc.md",
}


def _find_i18n_config(plugins: object) -> dict[str, object] | None:
    if not isinstance(plugins, list):
        return None
    for plugin in plugins:
        if not (isinstance(plugin, dict) and "i18n" in plugin):
            continue
        i18n_cfg = plugin.get("i18n")
        if isinstance(i18n_cfg, dict):
            return i18n_cfg
        return None
    return None


def _parse_i18n_languages(
    languages: object, *, fallback_default: str
) -> tuple[set[str], str]:
    locales: set[str] = set()
    default_locale = fallback_default
    if not isinstance(languages, list):
        return locales, default_locale

    for ent in languages:
        if not isinstance(ent, dict):
            continue
        loc = ent.get("locale")
        if not loc:
            continue
        locale = str(loc)
        locales.add(locale)
        if ent.get("default") is True:
            default_locale = locale
    return locales, default_locale


def _load_i18n_locales(repo_root: Path) -> tuple[set[str], str]:
    """Load locales from mkdocs.yml i18n config.

    Returns a tuple of (locales, default_locale). Falls back to ({}, 'en') on error.
    """
    mkdocs_path = repo_root / "mkdocs.yml"
    fallback: tuple[set[str], str] = (set(), "en")
    try:
        data = yaml.safe_load(mkdocs_path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    if not isinstance(data, dict):
        return fallback

    i18n_cfg = _find_i18n_config(data.get("plugins", []) or [])
    if i18n_cfg is None:
        return fallback
    return _parse_i18n_languages(
        i18n_cfg.get("languages", []) or [], fallback_default="en"
    )


def _iter_markdown_files(repo_root: Path, docs_dir: Path) -> Iterable[Path]:
    """Yield Markdown files to validate.

    Include canonical docs plus focused EN parity scope:
    - default locale tree (full)
    - EN architecture core-loop docs
    - non-locale docs at repository docs root
    Skip other locale trees and archived content.
    """
    locales, default_locale = _load_i18n_locales(repo_root)
    for p in docs_dir.rglob("*.md"):
        rel = p.relative_to(docs_dir)
        parts = rel.parts
        if parts and parts[0] in locales:
            locale = parts[0]
            if locale == default_locale:
                pass
            elif locale == "en":
                if not (
                    len(parts) >= 3
                    and parts[1] == "architecture"
                    and parts[2] in EN_CORE_ARCH_DOCS
                ):
                    continue
            else:
                continue
        if "archive" in parts:
            continue
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
    for md in _iter_markdown_files(repo_root, docs_dir):
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
