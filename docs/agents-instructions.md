# Agent / Developer Instructions (synthesized)

QMTL은 외부 서브트리이므로 변경은 드물고 신중해야 함.

This document collects the actionable guidelines from `AGENTS.md` files across the repository and provides a single reference for contributors.

## Key policies

- qmtl subtree:
  - Always sync `qmtl/` with the remote upstream before starting work. Use the subtree commands in the root `AGENTS.md`.
  - If you modify `qmtl/`, add tests in `qmtl/tests/` and run `git subtree push --prefix=qmtl qmtl-subtree main` to reflect changes upstream.
  - QMTL 변경은 버그 수정 또는 여러 전략에서 재사용될 기능 추가에 한함
  - 전략 특화 코드는 상위 레포에서 구현

- Testing:
  - Run the full test suite without warnings:
    ```bash
    uv run -m pytest -W error
    ```
  - Add tests for any new feature under the `tests/` directory near the code (e.g., `qmtl/tests/` or `strategies/tests/`).

- Coding conventions (strategies):
  - Use `snake_case` for files and functions.
  - Node processor functions should be pure and end with `_node`.
  - DAG modules should end with `_dag.py` and use `qmtl.dag_manager` to orchestrate.

- AlphaDocs:
  - Store research docs in `docs/alphadocs/` and update `docs/alphadocs_registry.yml` when adding or changing documents.
  - When code is implemented from a doc, add a comment at the module top: `# Source: docs/alphadocs/<doc>.md`.
  - The `docs/alphadocs/ideas/` directory is version-controlled for history but is not an implementation target.
  - Only ideas refined by stronger models (e.g., `docs/alphadocs/ideas/gpt5pro/`) should proceed to implementation.

  - Prioritized GPT-5-Pro ideas:
    - Files under `docs/alphadocs/ideas/gpt5pro/` are considered higher-priority. Tag them in the registry (`status: prioritized`, `source_model: gpt5pro`).
    - Automated agents (Codex, Vibe, Copilot-style) should:
      - Automatically create an implementation branch/issue when they select a `gpt5pro` idea.
      - Append a short run log to PR descriptions: agent name, model, timestamp, and actions.
      - Ensure history entries are recorded in `docs/alphadocs_history.log` when moving or renaming these documents.

## PR checklist (short)
- Tests pass locally and in CI (`uv run -m pytest -W error`).
- If `qmtl/` changed: subtree push performed and verification included in PR.
- Docs updated when relevant and `docs/alphadocs_registry.yml` synchronized.

## Where files live
- GitHub templates, workflows and repository-level config live under `.github/`.
- Contribution and agent-specific guidelines live in `.github/CONTRIBUTING.md` and `docs/agents-instructions.md`.

## Helpful commands
- Sync subtree:
  ```bash
  git fetch qmtl-subtree main
  git subtree pull --prefix=qmtl qmtl-subtree main --squash
  git add qmtl && git commit -m "chore: bump qmtl subtree to latest"
  git subtree push --prefix=qmtl qmtl-subtree main
  ```

- Run tests:
  ```bash
  uv run -m pytest -W error
  ```

