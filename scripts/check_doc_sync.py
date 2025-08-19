#!/usr/bin/env python3
"""Verify alignment between AlphaDocs, registry, and module annotations."""

from pathlib import Path
import re
import sys

try:
    import yaml
except Exception as exc:  # pragma: no cover - dependency error
    print(f"PyYAML required: {exc}")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "alphadocs_registry.yml"
DOC_DIR = ROOT / "docs" / "alphadocs"

errors: list[str] = []

# Load registry
try:
    registry = yaml.safe_load(REGISTRY.read_text())
except FileNotFoundError:
    errors.append(f"Registry file missing: {REGISTRY}")
    registry = []

registry_docs = {entry["doc"]: entry.get("modules", []) for entry in registry}

# Check docs present in registry
actual_docs = sorted(
    rel
    for p in DOC_DIR.rglob("*.md")
    if p.name != "README.md" and "docs/alphadocs/ideas/" not in (rel := p.relative_to(ROOT).as_posix())
)
registry_doc_paths = set(registry_docs.keys())

docs_not_registered = sorted(set(actual_docs) - registry_doc_paths)
if docs_not_registered:
    errors.append("Docs not in registry: " + ", ".join(docs_not_registered))

missing_doc_files = sorted(
    doc for doc in registry_doc_paths if not (ROOT / doc).exists()
)
if missing_doc_files:
    errors.append("Docs listed but missing: " + ", ".join(missing_doc_files))

# Validate module annotations
source_pattern = re.compile(r"^# Source: (?P<path>.+)$", re.MULTILINE)
for doc_path, modules in registry_docs.items():
    for module in modules or []:
        mod_file = ROOT / module
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
for mod_file in ROOT.glob("strategies/nodes/**/*.py"):
    text = mod_file.read_text().splitlines()[:5]
    rel_mod = mod_file.relative_to(ROOT).as_posix()
    for line in text:
        m = source_pattern.match(line.strip())
        if m:
            doc = m.group("path")
            if doc not in registry_docs or rel_mod not in registry_docs.get(doc, []):
                errors.append(f"{rel_mod} annotation not registered")
            break

if errors:
    print("Doc sync check failed:\n" + "\n".join(errors))
    sys.exit(1)

print("Doc sync check passed")
