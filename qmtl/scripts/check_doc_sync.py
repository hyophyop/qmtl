#!/usr/bin/env python3
"""Verify alignment between AlphaDocs, registry, and QMTL module annotations."""

from pathlib import Path
import re
import sys

try:
    import yaml
except Exception as exc:  # pragma: no cover - dependency error
    print(f"PyYAML required: {exc}")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "alphadocs_registry.yml"
DOC_DIR = ROOT / "docs" / "alphadocs"
MODULE_ROOT = ROOT / "qmtl" / "qmtl"


def check_doc_sync(
    root: Path = ROOT,
    registry: Path = REGISTRY,
    doc_dir: Path = DOC_DIR,
    module_root: Path = MODULE_ROOT,
) -> list[str]:
    """Return list of doc-sync errors for the given root."""
    errors: list[str] = []

    try:
        registry_data = yaml.safe_load(registry.read_text())
    except FileNotFoundError:
        errors.append(f"Registry file missing: {registry}")
        return errors

    registry_docs = {entry["doc"]: entry.get("modules", []) for entry in registry_data}

    # Check docs present in registry
    actual_docs = sorted(
        rel
        for p in doc_dir.rglob("*.md")
        if p.name != "README.md" and "docs/alphadocs/ideas/" not in (rel := p.relative_to(root).as_posix())
    )
    registry_doc_paths = set(registry_docs.keys())

    docs_not_registered = sorted(set(actual_docs) - registry_doc_paths)
    if docs_not_registered:
        errors.append("Docs not in registry: " + ", ".join(docs_not_registered))

    missing_doc_files = sorted(
        doc for doc in registry_doc_paths if not (root / doc).exists()
    )
    if missing_doc_files:
        errors.append("Docs listed but missing: " + ", ".join(missing_doc_files))

    # Validate module annotations
    source_pattern = re.compile(r"^# Source: (?P<path>.+)$", re.MULTILINE)
    for doc_path, modules in registry_docs.items():
        for module in modules or []:
            mod_file = root / module
            if not mod_file.exists():
                errors.append(f"Module listed but missing: {module}")
                continue
            head = mod_file.read_text().splitlines()[:5]
            match = None
            for line in head:
                m = source_pattern.match(line.strip())
                if m:
                    match = m.group("path")
                    break
            if match != doc_path:
                errors.append(f"{module} missing Source comment for {doc_path}")

    # Check modules with Source comment but not in registry
    for mod_file in module_root.rglob("*.py"):
        text = mod_file.read_text().splitlines()[:5]
        rel_mod = mod_file.relative_to(root).as_posix()
        for line in text:
            m = source_pattern.match(line.strip())
            if m:
                doc = m.group("path")
                if doc not in registry_docs or rel_mod not in registry_docs.get(doc, []):
                    errors.append(f"{rel_mod} annotation not registered")
                break

    return errors


def main() -> int:
    errs = check_doc_sync()
    if errs:
        print("Doc sync check failed:\n" + "\n".join(errs))
        return 1
    print("Doc sync check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
