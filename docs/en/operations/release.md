---
title: "Release Process"
tags:
  - operations
author: "QMTL Team"
last_modified: 2026-01-11
---

{{ nav_links() }}

# Release Process

1. Update `CHANGELOG.md` with release notes and apply corresponding updates to related documentation.
2. The `archive-docs` command only archives `docs/ko` and `docs/en`.
   The default behavior is **copy**, and the output goes to `docs/archive/<version>/{ko,en}/`.
3. Use `--dry-run` to verify the planned archive paths safely.
4. Run the archive command to capture the previous version.
5. Record archived versions and their support status in the internal archive log (kept outside the published docs).
6. Regenerate `docs/ko/reference/CHANGELOG.md` and `docs/en/reference/CHANGELOG.md` with
   `python scripts/release_docs.py sync-changelog`.
7. Follow the release cut checklist to capture tags, releases, artifacts, and verification links.

## archive-docs example

```bash
# Safety check (no file changes)
python scripts/release_docs.py archive-docs --version 1.2.3 --dry-run

# Default copy mode (creates docs/archive/1.2.3/ko, docs/archive/1.2.3/en)
python scripts/release_docs.py archive-docs --version 1.2.3 --status supported

# Use move mode only when needed (destructive)
python scripts/release_docs.py archive-docs --version 1.2.3 --mode move
```

## Release 0.1 Cut Checklist

All items below must be recorded to complete the Release 0.1 cut. The release notes must include the links to the verification evidence.

### 1) Create the tag

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

### 2) Create the GitHub Release

- Create a GitHub Release from tag `v0.1.0`.
- In the release notes, include a summary from `CHANGELOG.md` plus the DoD verification links.
  - Example: CI run URL, execution logs/artifact location link

### 3) Build and attach artifacts

- Wheel: `uv pip wheel .` or `uv build --wheel`
- sdist: `python -m build`
- Output path: `.whl` and `.tar.gz` files are generated under `dist/` by default.
- Attach the `dist/` artifacts to the GitHub Release.

### 4) Record DoD verification

- Run the verification commands in [Release 0.1 Definition of Done (DoD)](release_0_1_definition_of_done.md).
- Add the evidence link (CI run or logs location) to the release notes.

{{ nav_links() }}
