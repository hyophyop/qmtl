# Ideas — alpha docs

This folder contains short-form ideas, experiments, and early-stage proposals related to strategy development, data transforms, and pipeline patterns.
These files are version-controlled for historical record only; do not implement directly from them.
Only ideas refined by stronger models in subdirectories (e.g., `gpt5pro/`) are intended for implementation.

Purpose
- Capture loosely-formed concepts and hypotheses that may later grow into full strategy design documents, implementation plans, or examples.
- Encourage low-friction sharing of early thoughts so the team can iterate quickly.

What belongs here
- One-page idea notes describing a single concept or experiment.
- Proof-of-concept notes and short experiments (data samples, expected outcomes).
- Links to longer documents, notebooks, or prototypes when relevant.
- Drafts that are not yet ready for the main docs catalog.

What does NOT belong
- Polished design documents that are ready for publishing — those should go to `docs/alphadocs/` root or the appropriate docs folder.
- Final production code (place code under `qmtl/` or `examples/`).

How to contribute
1. Create a new Markdown file in this folder. Use the file name format described below.
2. Add metadata at the top (YAML front matter) using the provided template.
3. Keep the content concise — 1–3 pages is recommended. Use headings, examples, and optionally small data snippets or figures.
4. When you want feedback, add the `needs-review` label to the front matter and create an issue or mention reviewers in the team chat.

File naming conventions
- Use lowercase alphanumeric words separated by hyphens, e.g. `non-linear-variation.md`.
- Prefix experimental proofs-of-concept with `poc-`, e.g. `poc-small-sample-filter.md`.
- Use a date prefix only when the idea is attached to a specific experiment date, e.g. `2025-08-12-adaptive-window.md`.

Front matter template
```
---
title: Short, clear title
author: Your Name
date: 2025-08-17
status: draft # draft | needs-review | archived | active
tags:
  - idea
  - poc
summary: Short one-line summary of the idea (max 140 chars)
---
```

Recommended structure
- Summary (1–2 sentences)
- Motivation (why this matters)
- Sketch (how it might work; bullet points or a small diagram)
- Data/Experiment plan (what you'd measure; minimal reproducible steps)
- Risks and open questions
- Next steps

Status labels and lifecycle
- draft: Early-stage idea, private to contributors until shared.
- needs-review: Ready for feedback — ping reviewers or file an issue.
- active: The idea is being actively worked on; move content to the main docs or examples when stable.
- archived: Deprecated or superseded ideas kept for history.

Review process
- Tag files `needs-review` in front matter and open a short issue with reviewer suggestions.
- Reviewers should comment with specific suggestions; substantial changes can be made in a follow-up commit.
- Once accepted for development, move the idea to `active` and, if it includes design details, promote it to `docs/alphadocs/` or `qmtl/examples/`.

Examples
- See other files in this folder for example formatting and content.

Notes
- Keep ideas readable by non-authors — brief context and explicit next steps help others pick them up.
- Prefer small, testable experiments over large vague plans; it's easier to iterate and learn quickly.
