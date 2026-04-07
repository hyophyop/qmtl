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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACEABILITY_DOC_STEM = "implementation_traceability"
TRACEABILITY_SOURCE_DOCS = (
    ("architecture", "design_principles"),
    ("architecture", "capability_map"),
    ("architecture", "semantic_types"),
    ("architecture", "decision_algebra"),
    ("contracts", "core_loop"),
    ("contracts", "world_lifecycle"),
    ("architecture", "core_loop_world_automation"),
    ("architecture", "rebalancing_contract"),
)
TRACEABILITY_SOURCE_STEMS = tuple(stem for _, stem in TRACEABILITY_SOURCE_DOCS)
VALID_TRACEABILITY_STATUSES = {
    "normative-only",
    "planned",
    "partial",
    "implemented",
}


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


def _docs_section_dir(
    root: Path, locale: str, section: str, *, i18n_enabled: bool
) -> Path:
    if i18n_enabled:
        return root / "docs" / locale / section
    return root / "docs" / section


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


def _extract_concept_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"Concept ID:\s*`?([A-Z0-9][A-Z0-9\-]+)`?", text)
    return matches


def _collect_normative_concepts(
    locale_docs: dict[str, dict[str, Path]]
) -> tuple[bool, dict[str, dict[str, str]], list[str]]:
    active = False
    errors: list[str] = []
    concepts_by_locale: dict[str, dict[str, str]] = {}

    for locale, docs_by_stem in locale_docs.items():
        concepts: dict[str, str] = {}
        for stem in TRACEABILITY_SOURCE_STEMS:
            path = docs_by_stem.get(stem)
            if path is None:
                continue
            active = True
            ids = _extract_concept_ids(path)
            if not ids:
                errors.append(f"[{locale}] Normative doc {path} is missing Concept ID markers")
                continue
            seen_in_doc: set[str] = set()
            for concept_id in ids:
                if concept_id in seen_in_doc:
                    errors.append(
                        f"[{locale}] Duplicate Concept ID {concept_id!r} found in {path}"
                    )
                    continue
                seen_in_doc.add(concept_id)
                if concept_id in concepts and concepts[concept_id] != stem:
                    errors.append(
                        f"[{locale}] Concept ID {concept_id!r} is declared in both "
                        f"{concepts[concept_id]!r} and {stem!r}"
                    )
                    continue
                concepts[concept_id] = stem
        concepts_by_locale[locale] = concepts

    if active and concepts_by_locale:
        reference_locale, reference_concepts = next(iter(concepts_by_locale.items()))
        reference_ids = set(reference_concepts)
        for locale, concepts in concepts_by_locale.items():
            ids = set(concepts)
            missing = sorted(reference_ids - ids)
            extra = sorted(ids - reference_ids)
            if missing:
                errors.append(
                    f"[{locale}] Missing Concept IDs present in {reference_locale}: {', '.join(missing)}"
                )
            if extra:
                errors.append(
                    f"[{locale}] Extra Concept IDs not present in {reference_locale}: {', '.join(extra)}"
                )
            for concept_id in sorted(reference_ids & ids):
                if concepts[concept_id] != reference_concepts[concept_id]:
                    errors.append(
                        f"[{locale}] Concept ID {concept_id!r} maps to {concepts[concept_id]!r}, "
                        f"but {reference_locale} maps it to {reference_concepts[concept_id]!r}"
                    )
    return active, concepts_by_locale, errors


def _collect_traceability_source_docs(
    root: Path, required_locales: tuple[str, ...], *, i18n_enabled: bool
) -> dict[str, dict[str, Path]]:
    docs_by_locale: dict[str, dict[str, Path]] = {}
    for locale in required_locales:
        docs_by_stem: dict[str, Path] = {}
        for section, stem in TRACEABILITY_SOURCE_DOCS:
            path = _docs_section_dir(root, locale, section, i18n_enabled=i18n_enabled) / (
                f"{stem}.md"
            )
            if path.exists():
                docs_by_stem[stem] = path
        docs_by_locale[locale] = docs_by_stem
    return docs_by_locale


def _extract_traceability_entries(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"```ya?ml\n(.*?)```", text, flags=re.DOTALL)
    for block in matches:
        if "traceability:" not in block:
            continue
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(block) or {}
        except Exception as exc:
            raise RuntimeError(f"Failed to parse traceability YAML in {path}: {exc}") from exc
        entries = payload.get("traceability")
        if not isinstance(entries, list):
            raise RuntimeError(
                f"Traceability YAML in {path} must contain a 'traceability' list"
            )
        normalized: list[dict[str, object]] = []
        for raw in entries:
            if not isinstance(raw, dict):
                raise RuntimeError(f"Invalid traceability entry in {path}: {raw!r}")
            concept_id = str(raw.get("concept_id", "")).strip()
            source_doc = str(raw.get("source_doc", "")).strip()
            status = str(raw.get("status", "")).strip()
            code = raw.get("code") or []
            tests = raw.get("tests") or []
            if not isinstance(code, list) or not isinstance(tests, list):
                raise RuntimeError(
                    f"Traceability entry {concept_id or '<unknown>'} in {path} must use list-valued code/tests"
                )
            normalized.append(
                {
                    "concept_id": concept_id,
                    "source_doc": source_doc,
                    "status": status,
                    "code": [str(item).strip() for item in code if str(item).strip()],
                    "tests": [str(item).strip() for item in tests if str(item).strip()],
                }
            )
        return normalized
    raise RuntimeError(f"No traceability YAML block found in {path}")


def _collect_traceability_docs(
    root: Path,
    required_locales: tuple[str, ...],
    *,
    i18n_enabled: bool,
) -> tuple[dict[str, dict[str, dict[str, object]]], list[str]]:
    docs: dict[str, dict[str, dict[str, object]]] = {}
    errors: list[str] = []
    for locale in required_locales:
        path = _architecture_dir(root, locale, i18n_enabled=i18n_enabled) / (
            f"{TRACEABILITY_DOC_STEM}.md"
        )
        if not path.exists():
            errors.append(f"[{locale}] Missing traceability doc: {path}")
            continue
        try:
            entries = _extract_traceability_entries(path)
        except RuntimeError as exc:
            errors.append(f"[{locale}] {exc}")
            continue
        by_id: dict[str, dict[str, object]] = {}
        for entry in entries:
            concept_id = str(entry.get("concept_id", "")).strip()
            if not concept_id:
                errors.append(f"[{locale}] Traceability doc {path} has an entry without concept_id")
                continue
            if concept_id in by_id:
                errors.append(
                    f"[{locale}] Duplicate traceability entry for Concept ID {concept_id!r} in {path}"
                )
                continue
            by_id[concept_id] = entry
        docs[locale] = by_id
    return docs, errors


def _validate_traceability(
    root: Path,
    concepts_by_locale: dict[str, dict[str, str]],
    traceability_docs: dict[str, dict[str, dict[str, object]]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not concepts_by_locale:
        return errors, warnings

    for locale, concepts in concepts_by_locale.items():
        entries = traceability_docs.get(locale, {})
        missing = sorted(set(concepts) - set(entries))
        extra = sorted(set(entries) - set(concepts))
        if missing:
            errors.append(
                f"[{locale}] Missing traceability entries for Concept IDs: {', '.join(missing)}"
            )
        if extra:
            errors.append(
                f"[{locale}] Traceability entries reference unknown Concept IDs: {', '.join(extra)}"
            )

        for concept_id, source_stem in sorted(concepts.items()):
            entry = entries.get(concept_id)
            if entry is None:
                continue
            source_doc = str(entry.get("source_doc", "")).strip()
            expected_source = f"{source_stem}.md"
            if source_doc != expected_source:
                errors.append(
                    f"[{locale}] Traceability entry {concept_id!r} references source_doc={source_doc!r}, "
                    f"expected {expected_source!r}"
                )
            status = str(entry.get("status", "")).strip()
            if status not in VALID_TRACEABILITY_STATUSES:
                errors.append(
                    f"[{locale}] Traceability entry {concept_id!r} uses invalid status {status!r}"
                )
                continue

            code_paths = [Path(p) for p in entry.get("code", [])]  # type: ignore[arg-type]
            test_paths = [Path(p) for p in entry.get("tests", [])]  # type: ignore[arg-type]

            if status == "implemented":
                if not code_paths:
                    errors.append(
                        f"[{locale}] Implemented Concept ID {concept_id!r} must list at least one code path"
                    )
                if not test_paths:
                    errors.append(
                        f"[{locale}] Implemented Concept ID {concept_id!r} must list at least one test path"
                    )
            if status == "partial" and not code_paths:
                errors.append(
                    f"[{locale}] Partial Concept ID {concept_id!r} must list at least one code path"
                )

            for label, paths in (("code", code_paths), ("test", test_paths)):
                for rel_path in paths:
                    abs_path = root / rel_path
                    if not abs_path.exists():
                        errors.append(
                            f"[{locale}] Traceability entry {concept_id!r} references missing {label} path: {rel_path}"
                        )

    if traceability_docs:
        reference_locale, reference_entries = next(iter(traceability_docs.items()))
        reference_ids = set(reference_entries)
        for locale, entries in traceability_docs.items():
            ids = set(entries)
            missing = sorted(reference_ids - ids)
            extra = sorted(ids - reference_ids)
            if missing:
                errors.append(
                    f"[{locale}] Traceability doc is missing Concept IDs present in {reference_locale}: {', '.join(missing)}"
                )
            if extra:
                errors.append(
                    f"[{locale}] Traceability doc has extra Concept IDs not present in {reference_locale}: {', '.join(extra)}"
                )
    return errors, warnings


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

    traceability_source_docs = _collect_traceability_source_docs(
        root, required_locales, i18n_enabled=i18n_enabled
    )
    traceability_active, concepts_by_locale, concept_errors = _collect_normative_concepts(
        traceability_source_docs
    )
    errors.extend(concept_errors)
    if traceability_active:
        traceability_docs, traceability_errors = _collect_traceability_docs(
            root, required_locales, i18n_enabled=i18n_enabled
        )
        errors.extend(traceability_errors)
        traceability_doc_errors, traceability_warnings = _validate_traceability(
            root, concepts_by_locale, traceability_docs
        )
        errors.extend(traceability_doc_errors)
        warnings.extend(traceability_warnings)

    strict = os.getenv("DRIFT_STRICT", "0") == "1"
    return _build_result(errors, warnings, strict=strict)


def main() -> int:
    code, msg = check_design_drift()
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
