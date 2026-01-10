---
title: "Release Process"
tags:
  - operations
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Release Process

1. Update `CHANGELOG.md` with release notes and apply corresponding updates to related documentation.
2. Archive documentation for the previous version using `python scripts/release_docs.py archive-docs --version <version>`.
3. Record archived versions and their support status in the internal archive log (kept outside the published docs).
4. Regenerate `docs/ko/reference/CHANGELOG.md` and `docs/en/reference/CHANGELOG.md` with
   `python scripts/release_docs.py sync-changelog`.

{{ nav_links() }}
