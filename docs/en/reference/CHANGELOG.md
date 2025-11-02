---
title: "Changelog"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

<!-- Generated from ../CHANGELOG.md; do not edit manually -->

{{ nav_links() }}

# Changelog

## Unreleased

- `NodeCache.snapshot()` has been deprecated in favor of the read-only `CacheView` returned by `NodeCache.view()`. Strategy code should avoid calling the snapshot helper.
- Added `coverage()` and `fill_missing()` interfaces for history providers and removed `start`/`end` arguments from `StreamInput`.
- `TagQueryNode.resolve()` has been removed. Use `TagQueryManager.resolve_tags()` to fetch queue mappings before execution.
- Added `Node.add_tag()` to attach tags after node creation.

---

### Infra: Temporarily disable CI and document manual verification (2025-08-14)

PR title: ci: temporarily disable GitHub Actions auto triggers; update docs for manual verification (2025-08-14)

PR body:
```
## Changes
- Removed push/pull_request triggers from `.github/workflows/ci.yml` and `qmtl/.github/workflows/ci.yml`, leaving only `workflow_dispatch` (CI temporarily disabled).
- Added a CI downtime notice and local verification steps to `CONTRIBUTING.md`.

## Notes
- CI now runs manually; automatic validation on PRs and commits is paused.
- Please run linting, tests, and docs sync locally before opening PRs.
- The documentation and this entry will be updated when CI is restored.
```

{{ nav_links() }}
