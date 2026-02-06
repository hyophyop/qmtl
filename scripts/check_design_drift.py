#!/usr/bin/env python3
"""Design drift check: compare architecture docs spec versions with code.

The documentation tree is locale-scoped (mkdocs i18n). This checker reads the
default locale from ``mkdocs.yml`` and validates both:

- ``docs/<default_locale>/architecture/*.md``
- ``docs/en/architecture/*.md``

Each doc with front-matter ``spec_version`` must map to
``qmtl/foundation/spec.py::ARCH_SPEC_VERSIONS`` and each key in
``ARCH_SPEC_VERSIONS`` must have a matching doc file in required locale trees.

Exit codes:
- 0: Passed
- 1: Warning-only result
- 2: Hard failure (missing/mismatched versions or missing required docs)

Set ``DRIFT_STRICT=1`` to treat warnings as failures.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _find_i18n_config(plugins: object) -> dict[str, object] | None:
    if not isinstance(plugins, list):
        return None
    for entry in plugins:
        if not (isinstance(entry, dict) and "i18n" in entry):
            continue
        i18n_cfg = entry.get("i18n")
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

    for lang in languages:
        if not isinstance(lang, dict):
            continue
        loc = lang.get("locale")
        if not loc:
            continue
        locale = str(loc)
        locales.add(locale)
        if lang.get("default") is True:
            default_locale = locale
    return locales, default_locale


def _load_i18n_locales(root: Path) -> tuple[set[str], str, str | None]:
    """Return (configured_locales, default_locale, parse_error)."""
    mkdocs_path = root / "mkdocs.yml"
    fallback: tuple[set[str], str, str | None] = (set(), "ko", None)
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(mkdocs_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return set(), "ko", f"Failed to parse mkdocs.yml i18n configuration: {exc}"

    if not isinstance(data, dict):
        return fallback
    i18n_cfg = _find_i18n_config(data.get("plugins", []) or [])
    if i18n_cfg is None:
        return fallback
    locales, default_locale = _parse_i18n_languages(
        i18n_cfg.get("languages", []) or [], fallback_default="ko"
    )
    return locales, default_locale, None


def _required_arch_locales(root: Path) -> tuple[tuple[str, ...], bool, str | None]:
    """Return required locales, i18n flag, and optional parse error."""
    locales, default_locale, parse_error = _load_i18n_locales(root)
    if locales:
        required: list[str] = [default_locale]
        if "en" not in required:
            required.append("en")
        # Preserve insertion order and remove duplicates.
        return tuple(dict.fromkeys(required)), True, parse_error
    return ("legacy",), False, parse_error


def _architecture_dir(root: Path, locale: str, *, i18n_enabled: bool) -> Path:
    if i18n_enabled:
        return root / "docs" / locale / "architecture"
    return root / "docs" / "architecture"


def _read_front_matter(path: Path) -> dict[str, str]:
    """Parse a minimal YAML front-matter block into a dict.

    Only supports simple ``key: value`` pairs (strings). Stops at the second
    ``---``. Returns an empty dict when no front-matter is present.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        return {}
    lines = text.splitlines()[1:]
    out: dict[str, str] = {}
    for line in lines:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            out[key] = value
    return out


def _load_arch_spec_versions(root: Path) -> dict[str, str]:
    """Load ARCH_SPEC_VERSIONS directly from qmtl/foundation/spec.py."""
    spec_file = root / "qmtl" / "foundation" / "spec.py"
    ns: dict[str, object] = {}
    code = spec_file.read_text(encoding="utf-8")
    exec(compile(code, str(spec_file), "exec"), ns, ns)
    arch_spec_versions = ns.get("ARCH_SPEC_VERSIONS", {})
    if not isinstance(arch_spec_versions, dict):
        raise RuntimeError("ARCH_SPEC_VERSIONS not found or invalid in spec.py")
    out: dict[str, str] = {}
    for key, value in arch_spec_versions.items():
        out[str(key)] = str(value)
    return out


def _collect_locale_docs(
    root: Path, required_locales: tuple[str, ...], *, i18n_enabled: bool
) -> tuple[dict[str, dict[str, Path]], list[str], str | None]:
    locale_docs: dict[str, dict[str, Path]] = {}
    errors: list[str] = []
    for locale in required_locales:
        arch_dir = _architecture_dir(root, locale, i18n_enabled=i18n_enabled)
        if arch_dir.exists():
            docs = sorted(arch_dir.rglob("*.md"))
            nested = [doc for doc in docs if doc.parent != arch_dir]
            if nested:
                nested_list = ", ".join(str(path) for path in nested)
                errors.append(
                    f"[{locale}] Nested architecture docs are not supported by design drift check: {nested_list}"
                )
            locale_docs[locale] = {
                md.stem: md for md in docs if md.parent == arch_dir
            }
            continue
        if not i18n_enabled:
            return {}, errors, "No architecture docs; skipping design drift check"
        errors.append(f"[{locale}] Missing architecture docs directory: {arch_dir}")
    return locale_docs, errors, None


def _has_localized_architecture_dirs(root: Path) -> bool:
    docs_root = root / "docs"
    if not docs_root.exists():
        return False
    for locale_dir in docs_root.iterdir():
        if not locale_dir.is_dir():
            continue
        if (locale_dir / "architecture").exists():
            return True
    return False


def _doc_version_issues(
    locale: str, md: Path, *, code_ver: str | None, doc_ver: str | None
) -> tuple[str | None, str | None]:
    if code_ver is None and doc_ver is not None:
        return (
            f"[{locale}] Doc {md} declares spec_version={doc_ver} but no code mapping exists (qmtl/foundation/spec.py)",
            None,
        )
    if code_ver is not None and doc_ver is None:
        return None, (
            f"[{locale}] Doc {md} missing spec_version; expected {code_ver} in front-matter"
        )
    if code_ver is not None and doc_ver is not None and code_ver != doc_ver:
        return None, f"[{locale}] Version mismatch for {md}: docs={doc_ver} vs code={code_ver}"
    return None, None


def _collect_doc_version_issues(
    locale_docs: dict[str, dict[str, Path]], arch_spec_versions: dict[str, str]
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    for locale, docs_by_stem in locale_docs.items():
        for stem, md in docs_by_stem.items():
            doc_ver = _read_front_matter(md).get("spec_version")
            warning, error = _doc_version_issues(
                locale, md, code_ver=arch_spec_versions.get(stem), doc_ver=doc_ver
            )
            if warning:
                warnings.append(warning)
            if error:
                errors.append(error)
    return errors, warnings


def _missing_spec_doc_errors(
    root: Path,
    locale_docs: dict[str, dict[str, Path]],
    arch_spec_versions: dict[str, str],
    *,
    i18n_enabled: bool,
) -> list[str]:
    errors: list[str] = []
    for stem, code_ver in sorted(arch_spec_versions.items()):
        for locale, docs_by_stem in locale_docs.items():
            if stem in docs_by_stem:
                continue
            expected_doc = (
                _architecture_dir(root, locale, i18n_enabled=i18n_enabled) / f"{stem}.md"
            )
            errors.append(
                f"[{locale}] Missing architecture doc for spec key '{stem}': expected {expected_doc} (spec_version={code_ver})"
            )
    return errors


def _build_result(
    errors: list[str], warnings: list[str], *, strict: bool
) -> tuple[int, str]:
    if errors:
        msg = [
            "Design drift check failed:",
            *errors,
        ]
        if warnings:
            msg.extend(["", "Additional warnings:", *warnings])
        msg.extend(["", "Update qmtl/foundation/spec.py or docs front-matter to resolve."])
        return 2, "\n".join(msg)
    if warnings:
        msg = [
            "Design drift check warnings:",
            *warnings,
            "Set DRIFT_STRICT=1 to fail on warnings.",
        ]
        return (2 if strict else 1), "\n".join(msg)
    return 0, "Design drift check passed"


def check_design_drift(root: Path = ROOT) -> tuple[int, str]:
    # Avoid importing the qmtl.foundation package to prevent import-time cycles.
    # Load the spec file directly.
    try:
        arch_spec_versions = _load_arch_spec_versions(root)
    except Exception as exc:  # pragma: no cover - defensive
        return 2, f"Failed to load foundation spec: {exc}"

    required_locales, i18n_enabled, parse_error = _required_arch_locales(root)
    if parse_error and _has_localized_architecture_dirs(root):
        return (
            2,
            "Design drift check failed:\n"
            f"{parse_error}\n"
            "Fix mkdocs.yml parsing to avoid skipping locale-scoped architecture checks.",
        )
    locale_docs, errors, skip_message = _collect_locale_docs(
        root, required_locales, i18n_enabled=i18n_enabled
    )
    if skip_message is not None:
        return 0, skip_message

    doc_errors, warnings = _collect_doc_version_issues(locale_docs, arch_spec_versions)
    errors.extend(doc_errors)
    errors.extend(
        _missing_spec_doc_errors(
            root, locale_docs, arch_spec_versions, i18n_enabled=i18n_enabled
        )
    )
    strict = os.getenv("DRIFT_STRICT", "0") == "1"
    return _build_result(errors, warnings, strict=strict)


def main() -> int:
    code, msg = check_design_drift()
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
