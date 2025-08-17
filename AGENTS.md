# Development Guidelines

This repository hosts strategy experiments built on top of the [QMTL](qmtl/README.md) subtree. Use this document to keep workflows consistent and to leverage QMTL effectively.

- QMTL 수정은 버그 수정이나 QMTL 본체로 환원할 수 있는 범용 기능 추가에 한정합니다.
- 전략 전용 코드는 `strategies/`에 두고, QMTL 서브트리에 넣지 마세요.

## QMTL 서브트리 최신화 정책 (필수)

`qmtl/` 서브트리는 항상 원격 최신을 기준으로 작업해야 합니다.

- 작업(탐색, 코딩, 테스트) 시작 전 반드시 서브트리를 동기화하세요.
  ```bash
  git fetch qmtl-subtree main
  git subtree pull --prefix=qmtl qmtl-subtree main --squash
  ```
- 서브트리 갱신으로 변경사항이 생기면 루트 리포지토리에 커밋합니다.
  ```bash
  git add qmtl
  git commit -m "chore: bump qmtl subtree to latest"
  ```
- 로컬 수정 내용을 원본 저장소에 반영하려면 (필수):
  ```bash
  git subtree push --prefix=qmtl qmtl-subtree main
  ```
- 위 push 단계가 누락되면 원본 qmtl 저장소에 변경 사항이 남지 않습니다. 서브트리 작업 후 PR 전 반드시 실행하세요.
- 전략 개발 중 QMTL의 버그/개선을 발견하면 `qmtl/` 내부에서 우선 수정하고 테스트를 추가한 뒤, 위 절차로 서브트리를 업데이트하세요.
- PR 체크리스트에 포함:
  - [ ] `git log -n 3 --oneline qmtl/` 결과가 원격 최신과 일치함을 확인
  - [ ] `git subtree push --prefix=qmtl qmtl-subtree main` 으로 원본 저장소에 변경 사항을 반영했는지 확인
  - [ ] QMTL 변경 시 `qmtl/tests`와 루트 `tests` 모두 통과

### 빠른 점검 명령어

```bash
git log -n 3 --oneline qmtl/
git log -n 3 --oneline qmtl-subtree/main
```

## Setup

```bash
git remote add qmtl-subtree https://github.com/hyophyop/qmtl.git
uv venv
uv pip install -e qmtl[dev]
```
Install additional packages in the same environment when needed.
- The AlphaDocs sync script requires PyYAML; run `uv pip install pyyaml` if it's missing before executing `uv run scripts/check_doc_sync.py`.

## Development Practices

- Follow the Single Responsibility Principle for every strategy, generator, indicator and transform.
- Add reusable components under `strategies/`, `generators/`, `indicators/` or `transforms/`. Place tests in `qmtl/tests/` or a local `tests/` directory.
- 캔들·체결·호가창 등 raw 데이터에서 직접 얻을 수 없는 특징(feature)을 사용할 경우, 해당 중간 단계 기능이 `qmtl` extension에 이미 구현되어 있는지 먼저 확인하세요. 존재하면 이를 참조해 알파를 구현하고, 없다면 `qmtl` extension에 기능을 추가한 뒤 그 기능을 참조해 알파를 구현합니다.
- Manage node processors under `strategies/nodes/` and define strategy DAGs in `strategies/dags/`.
- Refer to `qmtl/architecture.md`, `qmtl/gateway.md` and `qmtl/dag-manager.md` for design details before modifying core behavior.
- See [strategies/README.md](strategies/README.md) for guidance on building and reusing node processors and DAGs.
- Use descriptive names and the `*_dsn` suffix for connection strings.
- When proposing task lists or improvements, highlight opportunities for parallel execution.
- Ensure resources such as network or database connections are closed to avoid `ResourceWarning`.
- 전략 개발 중 QMTL 이슈가 발견되면, 서브트리를 최신으로 동기화한 뒤 `qmtl/` 내부에서 우선 수정하고 테스트하세요. qmtl은 서브트리이지만 별도 구성된 프로젝트이므로 `qmtl/AGENTS.md`의 가이드를 충실히 따라 수정/테스트/커밋/PR을 진행해야 합니다. 수정 후 루트 리포지토리에 서브트리 변경사항을 커밋하는 것을 잊지 마세요.

## AlphaDocs Workflow

1. 모든 연구 문서는 `docs/alphadocs/`에 저장하고 `docs/alphadocs_registry.yml`에 `doc`, `status`, `modules` 필드를 갖는 항목을 추가합니다.
2. 문서를 근거로 코드를 작성할 때는 해당 모듈 상단에 `# Source: docs/alphadocs/<doc>.md` 주석을 포함합니다.
3. 구현이 완료되면 레지스트리의 `status`와 `modules` 목록을 갱신하고 관련 테스트를 추가합니다.
4. 문서를 이동하거나 이름을 변경할 경우 `docs/alphadocs_history.log`에 날짜, 이전 경로, 새 경로, 사유를 기록하고, 주석과 레지스트리 경로도 함께 수정합니다.
5. PR에는 레지스트리와 소스 주석 동기화를 확인했다는 체크 항목과 `uv run scripts/check_doc_sync.py` 실행 결과를 포함합니다.
6. 알파 문서는 구현에 사용된 위험(hazard), 방향(direction), 비용/체결(cost/fill) 등 모든 수학적 공식을 빠짐없이 포함해야 하며, 코드 노드는 이러한 공식을 참조하여 외부 데이터 입력에만 의존하지 말고 직접 구현해야 합니다. PR은 문서와 코드의 일치성을 보여주고 공식 구성요소를 다루는 테스트를 포함해야 합니다.

### Idea directories

- `docs/alphadocs/ideas/` 폴더는 아이디어 기록을 위한 버전 관리 대상일 뿐 직접 구현하지 않습니다.
- 더 높은 성능의 모델로 정제된 아이디어(예: `docs/alphadocs/ideas/gpt5pro/`)만 구현 대상으로 간주합니다.

### Prioritizing GPT-5-Pro Generated Ideas

- The `docs/alphadocs/ideas/gpt5pro/` directory contains alpha ideas rewritten and critiqued by a stronger model (GPT-5-Pro). Treat files in this directory as higher-priority implementation targets:
  - Mark these documents in `docs/alphadocs_registry.yml` with `status: prioritized` and include `source_model: gpt5pro` in the registry metadata.
  - When creating code from these documents, include `# Source: docs/alphadocs/ideas/gpt5pro/<doc>.md` and add `# Priority: gpt5pro` to the top of the module.
  - Agents and automated coding tools (Codex, Vibe, Copilot-style automation) should track history for these files in `docs/alphadocs_history.log`, create an implementation issue/branch automatically, and prefer them when selecting ideas to prototype or productionize.
  - PRs implementing `gpt5pro` ideas must include a short agent-run log (tool name, model, timestamp, high-level actions performed) as part of the PR description.

These measures ensure higher-fidelity ideas are visible to maintainers and to automated agents that can assist with implementation and history tracking.

## Testing

- Run the full test suite and treat warnings as errors:
  ```bash
  uv run -m pytest -W error
  ```
- Any change to node processors requires running their tests. Place tests under `strategies/tests/nodes/` and run them with:
  ```bash
  uv run -m pytest strategies/tests/nodes -W error
  ```
- Commit only after tests pass without warnings.

## Running Strategies

- Update `strategy.py` to execute your strategy and verify with:
  ```bash
  python strategy.py
  ```

