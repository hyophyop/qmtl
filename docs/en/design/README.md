---
title: "Design Docs"
tags: [design, docs]
author: "QMTL Team"
last_modified: 2025-12-15
---

# Design Docs

This directory (`docs/en/design/`) contains **design documents written to improve QMTL**.  
The goal is not just to “save ideas”, but to make them **actionable and reflectable** in architecture and implementation.

## `design/` vs `design/icebox/`

- `docs/en/design/`:
  - Holds **active design docs** intended to be reflected (or already being reflected).
  - These docs serve as a working baseline for review/implementation (while the final SSOT remains the code and `docs/en/architecture/`).
- `docs/en/design/icebox/`:
  - Holds **reference-only docs that are not current work items**.
  - Spike notes, drafts/sketches, past proposals, and ideas not yet adopted live here.
  - Content may be outdated or partially applicable; when linking, explicitly label it as “icebox (reference-only)”, and promote adopted parts into architecture/code.

## Lifecycle (post-implementation cleanup)

Design docs are **working documents for implementation**. Once implementation is complete:

1) Fold decisions/contracts/invariants into `docs/en/architecture/` (and `docs/en/operations/` if needed) plus code/tests to keep a single SSOT.  
2) **Archive or delete** the design doc.
   - If the historical context/decision record is still useful, move it to `docs/en/archive/` and mark `status: archived`.
   - If everything has been fully absorbed into official docs and it no longer provides value, delete it.

## Linking guidance

- When you link `design/icebox/*`, annotate the link text or sentence with **“icebox (reference-only, not an active work item)”**.
- For normative decisions/invariants/operational contracts, move the final form into `docs/en/architecture/` or code/tests to keep a single SSOT.

## i18n

Korean (`docs/ko/...`) is the canonical source; English (`docs/en/...`) is a translation.  
See the [Docs Internationalization guide](../guides/docs_internationalization.md) for rules.
