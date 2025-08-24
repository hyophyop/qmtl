# Copilot / Automated Agent Instructions

This file provides concise instructions for automated coding agents (Copilot-style assistants, Codex, Vibe, etc.) operating on this repository.

- Priority documents:
  - Files under `docs/alphadocs/ideas/gpt5pro/` are treated as higher-priority alpha ideas. These are ideas rewritten and critiqued by a stronger model (GPT-5-Pro) and are expected to be better candidates for implementation.

- Action expectations for agents:
  - When selecting ideas to implement, prefer `gpt5pro` documents.
  - Create an implementation branch and/or issue automatically with a short summary and link to the source document.
  - Record any moves/renames in `docs/alphadocs_history.log` with date, old path, new path, and reason.
  - When generating code from a doc, include these top-of-file comments in generated modules:
    - `# Source: docs/alphadocs/ideas/gpt5pro/<doc>.md`
    - `# Priority: gpt5pro`
  - Append a short agent-run log to the PR description: agent/tool name, model (if applicable), timestamp, and high-level actions performed.

- Registry annotation:
  - Update `docs/alphadocs_registry.yml` to set `status: prioritized` and `source_model: gpt5pro` for implemented or prioritized docs in this directory.

- Safety and review:
  - Do not directly merge large or high-risk code changes without human review. Create PRs and add `review-required: true` in the PR body for `gpt5pro` implementations.

These instructions supplement the shared policies in `CONTRIBUTING.md` and the brief summaries in `AGENTS.md` and `docs/agents-instructions.md`.
