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
3. Record archived versions and their support status in `docs/archive/README.md`.
4. Regenerate the documentation changelog with `python scripts/release_docs.py sync-changelog`.

{{ nav_links() }}
