---
title: "Release Process"
tags:
  - operations
author: "QMTL Team"
last_modified: 2026-01-10
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

## archive-docs example

```bash
# Safety check (no file changes)
python scripts/release_docs.py archive-docs --version 1.2.3 --dry-run

# Default copy mode (creates docs/archive/1.2.3/ko, docs/archive/1.2.3/en)
python scripts/release_docs.py archive-docs --version 1.2.3 --status supported

# Use move mode only when needed (destructive)
python scripts/release_docs.py archive-docs --version 1.2.3 --mode move
```

{{ nav_links() }}
